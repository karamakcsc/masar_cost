import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_link_to_form, get_weekday, now, nowtime, today
from frappe.utils.user import get_users_with_role
from rq.timeouts import JobTimeoutException

import erpnext
from erpnext.accounts.utils import (
    check_if_stock_and_account_balance_synced,
    update_gl_entries_after,
)
from erpnext.stock.stock_ledger import get_items_to_be_repost, repost_future_sle



def repost_sl_entries(doc):
    if doc.based_on == 'Item and Warehouse':
        args = {}
        args['time_format'] = '%H:%i:%s'
        args['item_code'] = doc.item_code
        args['posting_date'] = doc.posting_date
        args['posting_time'] = doc.posting_time
        #Get Previous Stock Ledger
        previous_sle = get_previous_sle(doc)
        values_dict = {
                'previus_sle': previous_sle.name,
                'qty_after_transaction': previous_sle.qty_after_transaction,
                'valuation_rate': previous_sle.valuation_rate,
                'stock_value': previous_sle.stock_value,
                'prev_stock_value': 0,
                'stock_value_difference': previous_sle.stock_value_difference,
            }

        args['voucher_no'] = previous_sle.voucher_no
        entries_to_fix = list(get_future_sle(args))
        i = 0
        while i < len(entries_to_fix):
            sle = entries_to_fix[i]
            i += 1
            process_sle(sle)
        # #Fetch Stock Ledger
        # for d in frappe.get_list("Stock Ledger Entry", fields=("name"), filters={"item_code": doc.item_code},order_by="posting_date"):
        #
        #     sle = frappe.get_doc('Stock Ledger Entry', d.name)

def get_previous_sle(args):
    sle = frappe.db.sql("""
         select *, timestamp(posting_date, posting_time) as "timestamp"
            from `tabStock Ledger Entry`
            where item_code = %(item_code)s
                and is_cancelled = 0
            and timestamp(posting_date, time_format(posting_time, %(time_format)s)) < timestamp(%(posting_date)s, time_format(%(posting_time)s, %(time_format)s))
            order by timestamp(posting_date, posting_time) desc, creation desc
            limit 1
            for update""",args, as_dict=True)
    return sle[0] if sle else frappe._dict()

def get_future_sle(args):
    return frappe.db.sql("""
        select *, timestamp(posting_date, posting_time) as "timestamp"
        from `tabStock Ledger Entry`
        where
            item_code = %(item_code)s
            and voucher_no != %(voucher_no)s
            and timestamp(posting_date, posting_time) >= timestamp(%(posting_date)s, %(posting_time)s)
            and is_cancelled = 0
        order by timestamp(posting_date, posting_time) asc
    """, args, as_dict=1)
