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

class _StockController(AccountsController):
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
					if warehouse_account.get(sle.warehouse):
						# from warehouse account

						self.check_expense_account(item_row)

						# If the item does not have the allow zero valuation rate flag set
						# and ( valuation rate not mentioned in an incoming entry
						# or incoming entry not found while delivering the item),
						# try to pick valuation rate from previous sle or Item master and update in SLE
						# Otherwise, throw an exception

						if not sle.stock_value_difference and self.doctype != "Stock Reconciliation" \
							and not item_row.get("allow_zero_valuation_rate"):

							sle = self.update_stock_ledger_entries(sle)

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
							"remarks": self.get("remarks") or "Accounting Entry for Stock",
							"debit": flt(sle.stock_value_difference_for_all_warehouses, precision),
							"is_opening": item_row.get("is_opening") or self.get("is_opening") or "No",
						}, warehouse_account[sle.warehouse]["account_currency"], item=item_row))

						gl_list.append(self.get_gl_dict({
							"account": expense_account,
							"against": warehouse_account[sle.warehouse]["account"],
							"cost_center": item_row.cost_center,
							"remarks": self.get("remarks") or "Accounting Entry for Stock",
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
