import functools

import frappe

from ecommerce_core.ecommerce_core.doctype.ecommerce_integration_log.ecommerce_integration_log import (
	create_log,
)


def create_integration_log(integration: str, **kwargs):
	"""Create or update an Ecommerce Integration Log for the given integration."""
	return create_log(module_def=integration, **kwargs)


def integration_log_wrapper(integration: str):
	"""Return a provider-specific logging function bound to an integration."""

	def log(**kwargs):
		return create_integration_log(integration, **kwargs)

	return log


def make_scheduler_error_logger(integration: str):
	"""Return a decorator that logs unhandled scheduled job errors.

	This preserves the existing provider behavior: exceptions are recorded and
	not re-raised, so scheduler jobs do not fail noisily after logging.
	"""

	log = integration_log_wrapper(integration)

	def decorator(fn):
		@functools.wraps(fn)
		def wrapper(*args, **kwargs):
			try:
				return fn(*args, **kwargs)
			except Exception as e:
				log(status="Error", exception=e, rollback=True)

		return wrapper

	return decorator


def run_integration_job(
	integration: str,
	fn,
	*args,
	request_id: str | None = None,
	method: str | None = None,
	request_data=None,
	set_user: str | None = None,
	success_status: str | None = "Success",
	error_status: str = "Error",
	rollback_on_error: bool = True,
	make_new_log: bool = True,
	clear_request_id: bool = True,
	**kwargs,
):
	"""Run provider code inside a shared Ecommerce Integration Log context."""
	previous_request_id = getattr(frappe.flags, "request_id", None)

	if request_id:
		log = frappe.get_doc("Ecommerce Integration Log", request_id)
	else:
		log = create_integration_log(
			integration,
			method=method,
			request_data=request_data,
			make_new=make_new_log,
		)
		request_id = log.name

	try:
		if set_user:
			# nosemgrep: frappe-setuser
			frappe.set_user(set_user)

		frappe.flags.request_id = request_id
		result = fn(*args, **kwargs)
	except Exception as e:
		create_integration_log(
			integration,
			status=error_status,
			exception=e,
			rollback=rollback_on_error,
		)
		return None
	else:
		if success_status:
			create_integration_log(integration, status=success_status)
		return result
	finally:
		if clear_request_id:
			frappe.flags.request_id = previous_request_id
