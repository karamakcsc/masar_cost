from json import loads

import frappe
import frappe.defaults
from frappe import _, throw
from frappe.model.meta import get_field_precision
from frappe.utils import cint, cstr, flt, formatdate, get_number_format_info, getdate, now, nowdate
from six import string_types

import erpnext

# imported to enable erpnext.accounts.utils.get_account_currency
from erpnext.accounts.doctype.account.account import get_account_currency  # noqa
from erpnext.stock import get_warehouse_account_map
from erpnext.stock.utils import get_stock_value_on


class StockValueAndAccountBalanceOutOfSync(frappe.ValidationError): pass
class FiscalYearError(frappe.ValidationError): pass
class PaymentEntryUnlinkError(frappe.ValidationError): pass


def get_future_stock_vouchers(posting_date, posting_time, for_warehouses=None, for_items=None, company=None):

	values = []
	condition = ""
	if for_items:
		condition += " and item_code in ({})".format(", ".join(["%s"] * len(for_items)))
		values += for_items

	# if for_warehouses:
	# 	condition += " and warehouse in ({})".format(", ".join(["%s"] * len(for_warehouses)))
	# 	values += for_warehouses

	if company:
		condition += " and company = %s"
		values.append(company)

	future_stock_vouchers = frappe.db.sql("""select distinct sle.voucher_type, sle.voucher_no
		from `tabStock Ledger Entry` sle
		where
			timestamp(sle.posting_date, sle.posting_time) >= timestamp(%s, %s)
			and is_cancelled = 0
			{condition}
		order by timestamp(sle.posting_date, sle.posting_time) asc, creation asc for update""".format(condition=condition),
		tuple([posting_date, posting_time] + values), as_dict=True)

	return [(d.voucher_type, d.voucher_no) for d in future_stock_vouchers]

def check_if_stock_and_account_balance_synced(posting_date, company, voucher_type=None, voucher_no=None):
	if not cint(erpnext.is_perpetual_inventory_enabled(company)):
		return

	# accounts = get_stock_accounts(company, voucher_type, voucher_no)
	# stock_adjustment_account = frappe.db.get_value("Company", company, "stock_adjustment_account")
	#
	# for account in accounts:
	# 	account_bal, stock_bal, warehouse_list = get_stock_and_account_balance(account,
	# 		posting_date, company)
	#
	# 	if abs(account_bal - stock_bal) > 0.1:
	# 		precision = get_field_precision(frappe.get_meta("GL Entry").get_field("debit"),
	# 			currency=frappe.get_cached_value('Company',  company,  "default_currency"))
	#
	# 		diff = flt(stock_bal - account_bal, precision)
	#
	# 		error_reason = _("Stock Value ({0}) and Account Balance ({1}) are out of sync for account {2} and it's linked warehouses as on {3}.").format(
	# 			stock_bal, account_bal, frappe.bold(account), posting_date)
	# 		error_resolution = _("Please create an adjustment Journal Entry for amount {0} on {1}")\
	# 			.format(frappe.bold(diff), frappe.bold(posting_date))
	#
	# 		frappe.msgprint(
	# 			msg="""{0}<br></br>{1}<br></br>""".format(error_reason, error_resolution),
	# 			raise_exception=StockValueAndAccountBalanceOutOfSync,
	# 			title=_('Values Out Of Sync'),
	# 			primary_action={
	# 				'label': _('Make Journal Entry'),
	# 				'client_action': 'erpnext.route_to_adjustment_jv',
	# 				'args': get_journal_entry(account, stock_adjustment_account, diff)
	# 			})
