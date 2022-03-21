from . import __version__ as app_version

app_name = "masar_cost"
app_title = "Moving Average Cost"
app_publisher = "KCSC"
app_description = "Modifications on Moving Average Cost"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "info@kcsc.com.jo"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/masar_cost/css/masar_cost.css"
# app_include_js = "/assets/masar_cost/js/masar_cost.js"

# include js, css files in header of web template
# web_include_css = "/assets/masar_cost/css/masar_cost.css"
# web_include_js = "/assets/masar_cost/js/masar_cost.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "masar_cost/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "masar_cost.install.before_install"
# after_install = "masar_cost.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "masar_cost.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
#	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"masar_cost.tasks.all"
# 	],
# 	"daily": [
# 		"masar_cost.tasks.daily"
# 	],
# 	"hourly": [
# 		"masar_cost.tasks.hourly"
# 	],
# 	"weekly": [
# 		"masar_cost.tasks.weekly"
# 	]
# 	"monthly": [
# 		"masar_cost.tasks.monthly"
# 	]
# }

# Testing
# -------

# before_tests = "masar_cost.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "masar_cost.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "masar_cost.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]


# User Data Protection
# --------------------

user_data_fields = [
	{
		"doctype": "{doctype_1}",
		"filter_by": "{filter_by}",
		"redact_fields": ["{field_1}", "{field_2}"],
		"partial": 1,
	},
	{
		"doctype": "{doctype_2}",
		"filter_by": "{filter_by}",
		"partial": 1,
	},
	{
		"doctype": "{doctype_3}",
		"strict": False,
	},
	{
		"doctype": "{doctype_4}"
	}
]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"masar_cost.auth.validate"
# ]
from masar_cost.override import _stock_ledger
from masar_cost.override import _bin
from masar_cost.override import _utils_stock
from masar_cost.override import _utils_accounts
from masar_cost.override import _stock_controller
from masar_cost.override._stock_controller import StockController
from erpnext.stock import stock_ledger
from erpnext.stock.doctype.bin import bin
from erpnext.stock import utils as utils_stock
from erpnext.accounts import utils as utils_accounts
from erpnext.controllers import stock_controller
from erpnext.controllers.stock_controller import StockController
from erpnext.stock.stock_ledger import update_entries_after
stock_ledger.make_sl_entries = _stock_ledger.make_sl_entries
stock_ledger.repost_future_sle = _stock_ledger.repost_future_sle
update_entries_after = _stock_ledger.update_entries_after
utils_stock.get_incoming_rate = _utils_stock.get_incoming_rate
utils_accounts.get_future_stock_vouchers = _utils_accounts.get_future_stock_vouchers
bin.update_qty = _bin.update_qty
stock_controller.StockController.get_gl_entries = _stock_controller.StockController.get_gl_entries
stock_controller.StockController.get_stock_ledger_details = _stock_controller.StockController.get_stock_ledger_details

#_stock_ledger.make_sl_entries --- Modified
#_stock_ledger.repost_current_voucher(args, allow_negative_stock=False, via_landed_cost_voucher=False): ---Not Modified
#_stock_ledger.get_args_for_future_sle(row): ---Not Modified
#_stock_ledger.make_entry(args, allow_negative_stock=False, via_landed_cost_voucher=False): ---Not Modified
# _stock_ledger.update_entries_after.initialize_previous_data --- Modified
# _stock_ledger.update_entries_after.process_sle --- Modified
# _stock_ledger.update_entries_after.get_moving_average_values --- Modified
#_stock_ledger.update_entries_after.update_bin --- Modified
#_stock_ledger.validate_negative_qty_in_future_sle --- Modified
# _stock_ledger.get_previous_sle_of_current_voucher(args, exclude_current_voucher=False): ---Not Modified
# _stock_ledger.get_previous_sle_of_current_voucher_for_all_warehouses(args, exclude_current_voucher=False): ---New
#_stock_ledger.update_qty_in_future_sle --- Modified
# _stock_ledger.get_future_sle_with_negative_qty_for_all_warehouses(args): ------New
# _stock_ledger.get_next_stock_reco(args): ---Not Modified
#_utils.get_incoming_rate ---Modified
#_bin.update_qty ---Modified
# _bin.get_bin_details(bin_name): ---Not Modified
#_StockController.get_gl_entries ---Modified
