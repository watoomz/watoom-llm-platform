extends RefCounted
## Base class for project tests run by `gg_ui.py test`.
##
##   extends "res://addons/gg/lib/gg_test.gd"
##   func test_damage() -> void:
##       eq(Combat.damage(10, 2.0), 20, "attack 10 x crit 2")
##
## Every method named test_* in res://tests/test_*.gd is one test (it may await). before_each() runs before each test.
## Assertions never throw: they record a failure and the test carries on, so one run lists every broken check.
var _failures: Array = []
var _checks: int = 0

func ok(cond: bool, msg: String = "") -> void:
	_checks += 1
	if not cond:
		_failures.append(msg if msg != "" else "ok(): condition was false")

func eq(got, want, msg: String = "") -> void:
	_checks += 1
	var same := false
	if (got is int or got is float) and (want is int or want is float):
		same = is_equal_approx(float(got), float(want))
	else:
		same = typeof(got) == typeof(want) and got == want
	if not same:
		_failures.append("%s: got %s, wanted %s" % [msg if msg != "" else "eq()", var_to_str(got), var_to_str(want)])

func near(got: float, want: float, tol: float = 0.001, msg: String = "") -> void:
	_checks += 1
	if absf(got - want) > tol:
		_failures.append("%s: got %s, wanted %s +- %s" % [msg if msg != "" else "near()", got, want, tol])

func between(got: float, lo: float, hi: float, msg: String = "") -> void:
	_checks += 1
	if got < lo or got > hi:
		_failures.append("%s: %s is outside [%s, %s]" % [msg if msg != "" else "between()", got, lo, hi])

func fail(msg: String) -> void:
	_checks += 1
	_failures.append(msg)
