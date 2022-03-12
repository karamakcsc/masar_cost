import frappe
from frappe.model.document import Document
from frappe.utils import flt


def update_qty(bin_name, args):
	from erpnext.controllers.stock_controller import future_sle_exists
	bin_details = get_bin_details(bin_name)
	# actual qty is already updated by processing current voucher
	actual_qty = bin_details.actual_qty
	actual_qty_for_all_warehouses = bin_details.actual_quantity_for_all_warehouses

	# actual qty is not up to date in case of backdated transaction
	if future_sle_exists(args):
		actual_qty = frappe.db.get_value("Stock Ledger Entry",
				filters={
					"item_code": args.get("item_code"),
					"warehouse": args.get("warehouse"),
					"is_cancelled": 0
				},
				fieldname="qty_after_transaction",
				order_by="posting_date desc, posting_time desc, creation desc",
			) or 0.0

		actual_qty_for_all_warehouses = frappe.db.get_value("Stock Ledger Entry",
				filters={
					"item_code": args.get("item_code"),
					"warehouse": args.get("warehouse"),
					"is_cancelled": 0
				},
				fieldname="qty_after_transaction_for_all_warehouses",
				order_by="posting_date desc, posting_time desc, creation desc",
			) or 0.0

	ordered_qty = flt(bin_details.ordered_qty) + flt(args.get("ordered_qty"))
	reserved_qty = flt(bin_details.reserved_qty) + flt(args.get("reserved_qty"))
	indented_qty = flt(bin_details.indented_qty) + flt(args.get("indented_qty"))
	planned_qty = flt(bin_details.planned_qty) + flt(args.get("planned_qty"))


	# compute projected qty
	projected_qty = (flt(actual_qty) + flt(ordered_qty)
		+ flt(indented_qty) + flt(planned_qty) - flt(reserved_qty)
		- flt(bin_details.reserved_qty_for_production) - flt(bin_details.reserved_qty_for_sub_contract))

	frappe.db.set_value('Bin', bin_name, {
		'actual_qty': actual_qty,
		'actual_quantity_for_all_warehouses': actual_qty_for_all_warehouses,
		'ordered_qty': ordered_qty,
		'reserved_qty': reserved_qty,
		'indented_qty': indented_qty,
		'planned_qty': planned_qty,
		'projected_qty': projected_qty
	})
def get_bin_details(bin_name):
	return frappe.db.get_value('Bin', bin_name, ['actual_qty','actual_quantity_for_all_warehouses', 'ordered_qty',
	'reserved_qty', 'indented_qty', 'planned_qty', 'reserved_qty_for_production',
	'reserved_qty_for_sub_contract'], as_dict=1)
