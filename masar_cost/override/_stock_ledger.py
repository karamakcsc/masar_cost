from __future__ import unicode_literals

import copy
import json

import frappe
from frappe import _
from frappe.model.meta import get_field_precision
from frappe.utils import cint, cstr, flt, get_link_to_form, getdate, now
from six import iteritems

import erpnext
from erpnext.stock.utils import (
	get_bin,
	get_incoming_outgoing_rate_for_cancel,
	get_valuation_method,
)

def make_sl_entries(sl_entries, allow_negative_stock=False, via_landed_cost_voucher=False):
	from erpnext.controllers.stock_controller import future_sle_exists
	if sl_entries:
		from erpnext.stock.utils import update_bin
		from masar_cost.override._utils import update_bin_for_all_warehouses

		cancel = sl_entries[0].get("is_cancelled")
		if cancel:
			validate_cancellation(sl_entries)
			set_as_cancel(sl_entries[0].get('voucher_type'), sl_entries[0].get('voucher_no'))

		args = get_args_for_future_sle(sl_entries[0])
		future_sle_exists(args, sl_entries)

		for sle in sl_entries:
			if sle.serial_no:
				validate_serial_no(sle)

			if cancel:
				sle['actual_qty'] = -flt(sle.get('actual_qty'))

				if sle['actual_qty'] < 0 and not sle.get('outgoing_rate'):
					sle['outgoing_rate'] = get_incoming_outgoing_rate_for_cancel(sle.item_code,
						sle.voucher_type, sle.voucher_no, sle.voucher_detail_no)
					sle['incoming_rate'] = 0.0

				if sle['actual_qty'] > 0 and not sle.get('incoming_rate'):
					sle['incoming_rate'] = get_incoming_outgoing_rate_for_cancel(sle.item_code,
						sle.voucher_type, sle.voucher_no, sle.voucher_detail_no)
					sle['outgoing_rate'] = 0.0

			if sle.get("actual_qty") or sle.get("voucher_type")=="Stock Reconciliation":
				sle_doc = make_entry(sle, allow_negative_stock, via_landed_cost_voucher)

			args = sle_doc.as_dict()

			if sle.get("voucher_type") == "Stock Reconciliation":
				# preserve previous_qty_after_transaction for qty reposting
				args.previous_qty_after_transaction = sle.get("previous_qty_after_transaction")

			#update_bin(args, allow_negative_stock, via_landed_cost_voucher)
			update_bin_for_all_warehouses(args, allow_negative_stock, via_landed_cost_voucher)

def get_args_for_future_sle(row):
	return frappe._dict({
		'voucher_type': row.get('voucher_type'),
		'voucher_no': row.get('voucher_no'),
		'posting_date': row.get('posting_date'),
		'posting_time': row.get('posting_time')
	})

def make_entry(args, allow_negative_stock=False, via_landed_cost_voucher=False):
	args.update({"doctype": "Stock Ledger Entry"})
	sle = frappe.get_doc(args)
	sle.flags.ignore_permissions = 1
	sle.allow_negative_stock=allow_negative_stock
	sle.via_landed_cost_voucher = via_landed_cost_voucher
	sle.insert()
	sle.submit()
	return sle

class update_entries_after(object):
	def initialize_previous_data(self, args):
		"""
			Get previous sl entries for current item for each related warehouse
			and assigns into self.data dict

			:Data Structure:

			self.data = {
				warehouse1: {
					'previus_sle': {},
					'qty_after_transaction': 10,
					'valuation_rate': 100,
					'stock_value': 1000,
					'prev_stock_value': 1000,
					'stock_queue': '[[10, 100]]',
					'stock_value_difference': 1000
				}
			}

		"""
		self.data.setdefault(args.warehouse, frappe._dict())
		warehouse_dict = self.data[args.warehouse]
		previous_sle = get_previous_sle_of_current_voucher(args)
		previous_sle_for_all_warehouses = get_previous_sle_of_current_voucher_for_all_warehouses(args)
		warehouse_dict.previous_sle = previous_sle

		for key in ("qty_after_transaction", "stock_value"):
			setattr(warehouse_dict, key, flt(previous_sle.get(key)))
		setattr(warehouse_dict, "valuation_rate", flt(previous_sle_for_all_warehouses.get("valuation_rate")))
		setattr(warehouse_dict, "qty_after_transaction_for_all_warehouses", flt(previous_sle_for_all_warehouses.get("qty_after_transaction_for_all_warehouses")))
		setattr(warehouse_dict, "stock_value_for_all_warehouses", flt(previous_sle_for_all_warehouses.get("stock_value_for_all_warehouses")))

		warehouse_dict.update({
			"prev_stock_value": previous_sle.stock_value or 0.0,
			"prev_stock_value_for_all_warehouses": previous_sle_for_all_warehouses.stock_value_for_all_warehouses or 0.0,
			"stock_queue": json.loads(previous_sle.stock_queue or "[]"),
			"stock_value_difference": 0.0,
			"stock_value_difference_for_all_warehouses": 0.0
		})

	def process_sle(self, sle):
			# previous sle data for this warehouse
			self.wh_data = self.data[sle.warehouse]
			if (sle.serial_no and not self.via_landed_cost_voucher) or not cint(self.allow_negative_stock):
				# validate negative stock for serialized items, fifo valuation
				# or when negative stock is not allowed for moving average
				if not self.validate_negative_stock(sle):
					self.wh_data.qty_after_transaction += flt(sle.actual_qty)
					self.wh_data.qty_after_transaction_for_all_warehouses += flt(sle.actual_qty)
					return

			# Get dynamic incoming/outgoing rate
			if not self.args.get("sle_id"):
				self.get_dynamic_incoming_outgoing_rate(sle)

			if sle.serial_no:
				self.get_serialized_values(sle)
				self.wh_data.qty_after_transaction += flt(sle.actual_qty)
				self.wh_data.qty_after_transaction_for_all_warehouses += flt(sle.actual_qty)
				if sle.voucher_type == "Stock Reconciliation":
					self.wh_data.qty_after_transaction = sle.qty_after_transaction
					self.wh_data.qty_after_transaction_for_all_warehouses = sle.qty_after_transaction_for_all_warehouses

				self.wh_data.stock_value = flt(self.wh_data.qty_after_transaction) * flt(self.wh_data.valuation_rate)
				self.wh_data.stock_value_for_all_warehouses = flt(self.wh_data.qty_after_transaction_for_all_warehouses) * flt(self.wh_data.valuation_rate)
			else:
				if sle.voucher_type=="Stock Reconciliation" and not sle.batch_no:
					# assert
					self.wh_data.valuation_rate = sle.valuation_rate
					self.wh_data.qty_after_transaction = sle.qty_after_transaction
					self.wh_data.qty_after_transaction_for_all_warehouses = sle.qty_after_transaction_for_all_warehouses
					self.wh_data.stock_queue = [[self.wh_data.qty_after_transaction, self.wh_data.valuation_rate]]
					self.wh_data.stock_value = flt(self.wh_data.qty_after_transaction) * flt(self.wh_data.valuation_rate)
					self.wh_data.stock_value_for_all_warehouses = flt(self.wh_data.qty_after_transaction_for_all_warehouses) * flt(self.wh_data.valuation_rate)
				else:
					if self.valuation_method == "Moving Average":
						self.get_moving_average_values(sle)
						self.wh_data.qty_after_transaction += flt(sle.actual_qty)
						self.wh_data.qty_after_transaction_for_all_warehouses += flt(sle.actual_qty)
						self.wh_data.stock_value = flt(self.wh_data.qty_after_transaction) * flt(self.wh_data.valuation_rate)
						self.wh_data.stock_value_for_all_warehouses = flt(self.wh_data.qty_after_transaction_for_all_warehouses) * flt(self.wh_data.valuation_rate)
					else:
						self.get_fifo_values(sle)
						self.wh_data.qty_after_transaction += flt(sle.actual_qty)
						self.wh_data.qty_after_transaction_for_all_warehouses += flt(sle.actual_qty)
						self.wh_data.stock_value = sum((flt(batch[0]) * flt(batch[1]) for batch in self.wh_data.stock_queue))

			# rounding as per precision
			self.wh_data.stock_value = flt(self.wh_data.stock_value, self.precision)
			self.wh_data.stock_value_for_all_warehouses = flt(self.wh_data.stock_value_for_all_warehouses, self.precision)
			stock_value_difference = self.wh_data.stock_value - self.wh_data.prev_stock_value
			stock_value_difference_for_all_warehouses = self.wh_data.stock_value_for_all_warehouses - self.wh_data.prev_stock_value_for_all_warehouses
			self.wh_data.prev_stock_value_for_all_warehouses = self.wh_data.stock_value_for_all_warehouses

			# update current sle
			sle.qty_after_transaction = self.wh_data.qty_after_transaction
			sle.qty_after_transaction_for_all_warehouses = self.wh_data.qty_after_transaction_for_all_warehouses
			sle.valuation_rate = self.wh_data.valuation_rate
			sle.stock_value = self.wh_data.stock_value
			sle.stock_value_for_all_warehouses = self.wh_data.stock_value_for_all_warehouses
			sle.stock_queue = json.dumps(self.wh_data.stock_queue)
			sle.stock_value_difference = stock_value_difference
			sle.stock_value_difference_for_all_warehouses = stock_value_difference_for_all_warehouses
			sle.doctype="Stock Ledger Entry"
			frappe.get_doc(sle).db_update()
			if not self.args.get("sle_id"):
				self.update_outgoing_rate_on_transaction(sle)

	def get_moving_average_values(self, sle):
		actual_qty = flt(sle.actual_qty)
		new_stock_qty = flt(self.wh_data.qty_after_transaction_for_all_warehouses) + actual_qty
		if new_stock_qty >= 0:
			if actual_qty > 0:
				if flt(self.wh_data.qty_after_transaction_for_all_warehouses) <= 0:
					self.wh_data.valuation_rate = sle.incoming_rate
				else:
					new_stock_value = (self.wh_data.qty_after_transaction_for_all_warehouses * self.wh_data.valuation_rate) + \
						(actual_qty * sle.incoming_rate)

					self.wh_data.valuation_rate = new_stock_value / new_stock_qty

			elif sle.outgoing_rate:
				if new_stock_qty:
					new_stock_value = (self.wh_data.qty_after_transaction_for_all_warehouses * self.wh_data.valuation_rate) + \
						(actual_qty * sle.outgoing_rate)

					self.wh_data.valuation_rate = new_stock_value / new_stock_qty
				else:
					self.wh_data.valuation_rate = sle.outgoing_rate
		else:
			if flt(self.wh_data.qty_after_transaction_for_all_warehouses) >= 0 and sle.outgoing_rate:
				self.wh_data.valuation_rate = sle.outgoing_rate

			if not self.wh_data.valuation_rate and actual_qty > 0:
				self.wh_data.valuation_rate = sle.incoming_rate

			# Get valuation rate from previous SLE or Item master, if item does not have the
			# allow zero valuration rate flag set
			if not self.wh_data.valuation_rate and sle.voucher_detail_no:
				allow_zero_valuation_rate = self.check_if_allow_zero_valuation_rate(sle.voucher_type, sle.voucher_detail_no)
				if not allow_zero_valuation_rate:
					self.wh_data.valuation_rate = get_valuation_rate(sle.item_code, sle.warehouse,
						sle.voucher_type, sle.voucher_no, self.allow_zero_rate,
						currency=erpnext.get_company_currency(sle.company))

	def validate_negative_qty_in_future_sle(args, allow_negative_stock=False):
		allow_negative_stock = cint(allow_negative_stock) \
			or cint(frappe.db.get_single_value("Stock Settings", "allow_negative_stock"))

		if (args.actual_qty < 0 or args.voucher_type == "Stock Reconciliation") and not allow_negative_stock:
			sle = get_future_sle_with_negative_qty(args)
			if sle:
				message = _("{0} units of {1} needed in {2} on {3} {4} for {5} to complete this transaction.").format(
					abs(sle[0]["qty_after_transaction"]),
					frappe.get_desk_link('Item', args.item_code),
					frappe.get_desk_link('Warehouse', args.warehouse),
					sle[0]["posting_date"], sle[0]["posting_time"],
					frappe.get_desk_link(sle[0]["voucher_type"], sle[0]["voucher_no"]))

				frappe.throw(message, NegativeStockError, title='Insufficient Stock')

			sle_for_all_warehouses = get_future_sle_with_negative_qty_for_all_warehouses(args)
			if sle_for_all_warehouses:
				message = _("{0} units of {1} needed in {2} on {3} {4} for {5} to complete this transaction.").format(
					abs(sle_for_all_warehouses[0]["qty_after_transaction_for_all_warehouses"]),
					frappe.get_desk_link('Item', args.item_code),
					sle_for_all_warehouses[0]["posting_date"], sle[0]["posting_time"],
					frappe.get_desk_link(sle_for_all_warehouses[0]["voucher_type"], sle_for_all_warehouses[0]["voucher_no"]))

				frappe.throw(message, NegativeStockError, title='Insufficient Stock')


def get_previous_sle_of_current_voucher(args, exclude_current_voucher=False):
	"""get stock ledger entries filtered by specific posting datetime conditions"""

	args['time_format'] = '%H:%i:%s'
	if not args.get("posting_date"):
		args["posting_date"] = "1900-01-01"
	if not args.get("posting_time"):
		args["posting_time"] = "00:00"

	voucher_condition = ""
	if exclude_current_voucher:
		voucher_no = args.get("voucher_no")
		voucher_condition = f"and voucher_no != '{voucher_no}'"

	sle = frappe.db.sql("""
		select *, timestamp(posting_date, posting_time) as "timestamp"
		from `tabStock Ledger Entry`
		where item_code = %(item_code)s
			and warehouse = %(warehouse)s
			and is_cancelled = 0
			{voucher_condition}
			and timestamp(posting_date, time_format(posting_time, %(time_format)s)) < timestamp(%(posting_date)s, time_format(%(posting_time)s, %(time_format)s))
		order by timestamp(posting_date, posting_time) desc, creation desc
		limit 1
		for update""".format(voucher_condition=voucher_condition), args, as_dict=1)

	return sle[0] if sle else frappe._dict()

def get_previous_sle_of_current_voucher_for_all_warehouses(args, exclude_current_voucher=False):
	"""get stock ledger entries filtered by specific posting datetime conditions"""

	args['time_format'] = '%H:%i:%s'
	if not args.get("posting_date"):
		args["posting_date"] = "1900-01-01"
	if not args.get("posting_time"):
		args["posting_time"] = "00:00"

	voucher_condition = ""
	if exclude_current_voucher:
		voucher_no = args.get("voucher_no")
		voucher_condition = f"and voucher_no != '{voucher_no}'"

	sle = frappe.db.sql("""
		select *, timestamp(posting_date, posting_time) as "timestamp"
		from `tabStock Ledger Entry`
		where item_code = %(item_code)s
			and is_cancelled = 0
			{voucher_condition}
			and timestamp(posting_date, time_format(posting_time, %(time_format)s)) < timestamp(%(posting_date)s, time_format(%(posting_time)s, %(time_format)s))
		order by timestamp(posting_date, posting_time) desc, creation desc
		limit 1
		for update""".format(voucher_condition=voucher_condition), args, as_dict=1)

	return sle[0] if sle else frappe._dict()

def update_qty_in_future_sle(args, allow_negative_stock=False):
	"""Recalculate Qty after Transaction in future SLEs based on current SLE."""
	datetime_limit_condition = ""
	qty_shift = args.actual_qty

	# find difference/shift in qty caused by stock reconciliation
	if args.voucher_type == "Stock Reconciliation":
		qty_shift = get_stock_reco_qty_shift(args)

	# find the next nearest stock reco so that we only recalculate SLEs till that point
	next_stock_reco_detail = get_next_stock_reco(args)
	if next_stock_reco_detail:
		detail = next_stock_reco_detail[0]
		# add condition to update SLEs before this date & time
		datetime_limit_condition = get_datetime_limit_condition(detail)

	frappe.db.sql("""
		update `tabStock Ledger Entry`
		set qty_after_transaction = qty_after_transaction + {qty_shift},
			qty_after_transaction_for_all_warehouses = qty_after_transaction_for_all_warehouses
		where
			item_code = %(item_code)s
			and warehouse = %(warehouse)s
			and voucher_no != %(voucher_no)s
			and is_cancelled = 0
			and (timestamp(posting_date, posting_time) > timestamp(%(posting_date)s, %(posting_time)s)
				or (
					timestamp(posting_date, posting_time) = timestamp(%(posting_date)s, %(posting_time)s)
					and creation > %(creation)s
				)
			)
		{datetime_limit_condition}
		""".format(qty_shift=qty_shift, datetime_limit_condition=datetime_limit_condition), args)

	validate_negative_qty_in_future_sle(args, allow_negative_stock)

def get_future_sle_with_negative_qty_for_all_warehouses(args):
	return frappe.db.sql("""
		select
			qty_after_transaction_for_all_warehouses, posting_date, posting_time,
			voucher_type, voucher_no
		from `tabStock Ledger Entry`
		where
			item_code = %(item_code)s
			and voucher_no != %(voucher_no)s
			and timestamp(posting_date, posting_time) >= timestamp(%(posting_date)s, %(posting_time)s)
			and is_cancelled = 0
			and qty_after_transaction_for_all_warehouses < 0
		order by timestamp(posting_date, posting_time) asc
		limit 1
	""", args, as_dict=1)
