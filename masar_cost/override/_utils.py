from __future__ import unicode_literals

import json

import frappe
import erpnext
from frappe import _
from frappe.utils import cstr, flt, get_link_to_form, nowdate, nowtime
from six import string_types



@frappe.whitelist()
def get_incoming_rate(args, raise_error_if_no_rate=True):
	"""Get Incoming Rate based on valuation method"""
	from erpnext.stock.stock_ledger import get_previous_sle, get_valuation_rate
	from erpnext.stock.utils import get_valuation_method
	from masar_cost.override._stock_ledger import get_previous_sle_of_current_voucher_for_all_warehouses

	if isinstance(args, string_types):
		args = json.loads(args)

	in_rate = 0
	if (args.get("serial_no") or "").strip():
		in_rate = get_avg_purchase_rate(args.get("serial_no"))
	else:
		valuation_method = get_valuation_method(args.get("item_code"))
		previous_sle = get_previous_sle(args)
		previous_sle_for_all_warehouses = get_previous_sle_of_current_voucher_for_all_warehouses(args)
		if valuation_method == 'FIFO':
			if previous_sle:
				previous_stock_queue = json.loads(previous_sle.get('stock_queue', '[]') or '[]')
				in_rate = get_fifo_rate(previous_stock_queue, args.get("qty") or 0) if previous_stock_queue else 0
		elif valuation_method == 'Moving Average':
			in_rate = previous_sle_for_all_warehouses.get('valuation_rate') or 0

	if not in_rate:
		voucher_no = args.get('voucher_no') or args.get('name')
		in_rate = get_valuation_rate(args.get('item_code'), args.get('warehouse'),
			args.get('voucher_type'), voucher_no, args.get('allow_zero_valuation'),
			currency=erpnext.get_company_currency(args.get('company')), company=args.get('company'),
			raise_error_if_no_rate=raise_error_if_no_rate)

	return flt(in_rate)

def update_bin_for_all_warehouses(args, allow_negative_stock=False, via_landed_cost_voucher=False):
	from erpnext.stock.doctype.bin.bin import update_stock
	is_stock_item = frappe.get_cached_value('Item', args.get("item_code"), 'is_stock_item')
	if is_stock_item:
			bin_exist = frappe.db.get_value("Bin", {"item_code": args.get("item_code"), "warehouse":args.get("warehouse")})
			if not bin_exist:
				bin_obj = frappe.get_doc({
					"doctype": "Bin",
					"item_code": args.get("item_code"),
					"warehouse": args.get("warehouse"),
				})
				bin_obj.flags.ignore_permissions = 1
				actual_qty = frappe.db.sql("""select sum(actual_qty) from tabBin
					where item_code='%s' """%(args.get("item_code")))
				actual_qty = actual_qty[0][0] if actual_qty else 0.0
				bin_obj.actual_quantity_for_all_warehouses = flt(actual_qty)
				bin_obj.insert()
				# update_qty_for_all_warehouses(bin_obj.name,args)
			for d in frappe.get_list("Bin", fields=("name"), filters={"item_code": args.get("item_code")}):
				bin = frappe.get_doc('Bin', d.name)
				update_stock(bin.name, args, allow_negative_stock, via_landed_cost_voucher)
			return bin
	else:
		frappe.msgprint(_("Item {0} ignored since it is not a stock item").format(args.get("item_code")))

def update_qty_for_all_warehouses(bin_name,args):
	bin_obj = _get_bin_details(bin_name)
	actual_qty = frappe.db.sql("""select sum(actual_qty) from tabBin
		where item_code='%s' """%(args.get("item_code")))
	actual_qty = actual_qty[0][0] if actual_qty else 0.0
	bin_obj.actual_quantity_for_all_warehouses = flt(actual_qty)

def _get_bin_details(bin_name):
	return frappe.db.get_value('Bin', bin_name, ['actual_qty','actual_quantity_for_all_warehouses', 'ordered_qty',
	'reserved_qty', 'indented_qty', 'planned_qty', 'reserved_qty_for_production',
	'reserved_qty_for_sub_contract'], as_dict=1)
