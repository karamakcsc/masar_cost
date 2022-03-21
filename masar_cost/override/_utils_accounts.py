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
