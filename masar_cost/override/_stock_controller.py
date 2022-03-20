import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, get_link_to_form, getdate

import erpnext
from erpnext.accounts.general_ledger import (
	make_gl_entries,
	make_reverse_gl_entries,
	process_gl_map,
)
from erpnext.accounts.utils import get_fiscal_year
from erpnext.controllers.accounts_controller import AccountsController
from erpnext.stock import get_warehouse_account_map
from erpnext.stock.stock_ledger import get_valuation_rate


class QualityInspectionRequiredError(frappe.ValidationError): pass
class QualityInspectionRejectedError(frappe.ValidationError): pass
class QualityInspectionNotSubmittedError(frappe.ValidationError): pass

class StockController(AccountsController):
	def get_gl_entries(self, warehouse_account=None, default_expense_account=None,
			default_cost_center=None):

		if not warehouse_account:
			warehouse_account = get_warehouse_account_map(self.company)

		sle_map = self.get_stock_ledger_details()
		voucher_details = self.get_voucher_details(default_expense_account, default_cost_center, sle_map)

		gl_list = []
		warehouse_with_no_account = []
		precision = self.get_debit_field_precision()
		for item_row in voucher_details:

			sle_list = sle_map.get(item_row.name)
			if sle_list:
				for sle in sle_list:
					#frappe.throw(str(sle.stock_value_difference))
					if warehouse_account.get(sle.warehouse):
						# from warehouse account

						self.check_expense_account(item_row)

						# expense account/ target_warehouse / source_warehouse
						if item_row.get('target_warehouse'):
							warehouse = item_row.get('target_warehouse')
							expense_account = warehouse_account[warehouse]["account"]
						else:
							expense_account = item_row.expense_account

						gl_list.append(self.get_gl_dict({
							"account": warehouse_account[sle.warehouse]["account"],
							"against": expense_account,
							"cost_center": item_row.cost_center,
							"project": item_row.project or self.get('project'),
							"remarks": self.get("remarks") or _("Accounting Entry for Stock"),
							"debit": flt(sle.stock_value_difference_for_all_warehouses, precision),
							"is_opening": item_row.get("is_opening") or self.get("is_opening") or "No",
						}, warehouse_account[sle.warehouse]["account_currency"], item=item_row))

						gl_list.append(self.get_gl_dict({
							"account": expense_account,
							"against": warehouse_account[sle.warehouse]["account"],
							"cost_center": item_row.cost_center,
							"remarks": self.get("remarks") or _("Accounting Entry for Stock"),
							"credit": flt(sle.stock_value_difference_for_all_warehouses, precision),
							"project": item_row.get("project") or self.get("project"),
							"is_opening": item_row.get("is_opening") or self.get("is_opening") or "No"
						}, item=item_row))
					elif sle.warehouse not in warehouse_with_no_account:
						warehouse_with_no_account.append(sle.warehouse)

		if warehouse_with_no_account:
			for wh in warehouse_with_no_account:
				if frappe.db.get_value("Warehouse", wh, "company"):
					frappe.throw(_("Warehouse {0} is not linked to any account, please mention the account in the warehouse record or set default inventory account in company {1}.").format(wh, self.company))

		return process_gl_map(gl_list, precision=precision)

	def get_stock_ledger_details(self):
		stock_ledger = {}
		stock_ledger_entries = frappe.db.sql("""
			select
				name, warehouse, stock_value_difference_for_all_warehouses, valuation_rate,
				voucher_detail_no, item_code, posting_date, posting_time,
				actual_qty, qty_after_transaction
			from
				`tabStock Ledger Entry`
			where
				voucher_type=%s and voucher_no=%s and is_cancelled = 0
		""", (self.doctype, self.name), as_dict=True)

		for sle in stock_ledger_entries:
			stock_ledger.setdefault(sle.voucher_detail_no, []).append(sle)
		return stock_ledger

def future_sle_exists(args, sl_entries=None):
	key = (args.voucher_type, args.voucher_no)

	if validate_future_sle_not_exists(args, key, sl_entries):
		return False
	elif get_cached_data(args, key):
		return True

	if not sl_entries:
		sl_entries = get_sle_entries_against_voucher(args)
		if not sl_entries:
			return

	or_conditions = get_conditions_to_validate_future_sle(sl_entries)

	data = frappe.db.sql("""
		select item_code, warehouse, count(name) as total_row
		from `tabStock Ledger Entry` force index (item_warehouse)
		where
			({})
			and timestamp(posting_date, posting_time)
				>= timestamp(%(posting_date)s, %(posting_time)s)
			and voucher_no != %(voucher_no)s
			and is_cancelled = 0
		GROUP BY
			item_code, warehouse
		""".format(" or ".join(or_conditions)), args, as_dict=1)

	for d in data:
		frappe.local.future_sle[key][(d.item_code, d.warehouse)] = d.total_row

	return len(data)

def validate_future_sle_not_exists(args, key, sl_entries=None):
	item_key = ''
	if args.get('item_code'):
		item_key = (args.get('item_code'))

	if not sl_entries and hasattr(frappe.local, 'future_sle'):
		if (not frappe.local.future_sle.get(key) or
			(item_key and item_key not in frappe.local.future_sle.get(key))):
			return True

def get_cached_data(args, key):
	if not hasattr(frappe.local, 'future_sle'):
		frappe.local.future_sle = {}

	if key not in frappe.local.future_sle:
		frappe.local.future_sle[key] = frappe._dict({})

	if args.get('item_code'):
		item_key = (args.get('item_code'))
		count = frappe.local.future_sle[key].get(item_key)

		return True if (count or count == 0) else False
	else:
		return frappe.local.future_sle[key]

def get_sle_entries_against_voucher(args):
	return frappe.get_all("Stock Ledger Entry",
		filters={"voucher_type": args.voucher_type, "voucher_no": args.voucher_no},
		fields=["item_code"],
		order_by="creation asc")

def get_conditions_to_validate_future_sle(sl_entries):
	items_map = {}
	for entry in sl_entries:
		if entry.item_code not in items_map:
			items_map[entry.item_code] = set()

	or_conditions = []
	for items in items_map.items():
		or_conditions.append(
			f"""item_code = {frappe.db.escape(item_code)}""")

	return or_conditions
