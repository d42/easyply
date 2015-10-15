"""

Implementation & usage notes:

Each rule, such as `production: SYM another (SYM another)?` is parsed
into a Rule object. It provides means of enumeration of possible expansions
of optional parameters and so on. The class itself and the parser are defined
in `nodes` and `parser`, respectively.

easyply is rather forgiving when it comes to input parameters and
employs implicit conversions where possible. In general, functions
accept either:

  + rulesets, which can be one of the following:
    + Rule object, passed as-is
    + list of Rule objects, passed as-is
    + string, parsed by `parser.parse` into a list of Rule objects
    + list of strings, each parsed by `parser.parse`
  + rule, which is a simply a ruleset containing one Rule object. It's
    coerced in the same way as the ruleset case and then checked
    for length. In case of length different than 1, `SingleRuleExpectedError`
    is raised.
"""
from __future__ import absolute_import

from itertools import chain
from functools import wraps

from six import string_types

from .parser import parse as _parse
from .nodes import NamedTerm


class NoDocstringError(Exception):
    pass


class SingleRuleExpectedError(Exception):
    pass


def _coerce_to_ruleset(ruleset):
    def coerce_to_rule(rule):
        if isinstance(rule, string_types):
            return _parse(rule)
        else:
            return (rule, )

    if not isinstance(ruleset, (list, tuple)):
        ruleset = (ruleset, )

    return list(chain.from_iterable(coerce_to_rule(rule) for rule in ruleset))


def _coerce_to_single_rule(rule):
    ruleset = _coerce_to_ruleset(rule)
    if len(ruleset) != 1:
        raise SingleRuleExpectedError(rule)

    return ruleset[0]


def expand_optionals(ruleset, format=True, pure_ply=True):
    """
      Takes a ruleset (see Implementation Notes) and returns a list of all
      possible optional term resolutions.
      The optional parameter `format` controls the output. If it's true,
      `expand_optionals` will output a list of strings. Otherwise a list of
      flattened Rule objects is returned.
    """

    def process_rule(rule):
        rules = rule.expand_optionals()
        if format:
            return list(set(rule.flatten().format(pure_ply) for rule in rules))
        else:
            return list(set(rule.flatten() for rule in rules))

    ruleset = _coerce_to_ruleset(ruleset)
    return list(chain.from_iterable(process_rule(rule) for rule in ruleset))


def create_wrapper(rule, func):
    """
      Takes a rule (either a Rule object or a string, see `expand_optionals`)
      and a function and returns the given function wrapped with expr as var:
      a decorator that provides:

        + Named parameters extraction from the `p` parameter.
        + PLY-compatible docstring (computed from the passed rule).
    """

    rule = _coerce_to_single_rule(rule)

    # flattening - we need to iterate over rule terms
    rule = rule.flatten()

    @wraps(func)
    def wrapper(p):
        kwargs = {}
        # named parameters extraction
        for i, term in enumerate(rule.terms):
            if isinstance(term, NamedTerm):
                kwargs[term.name] = p[i + 1]
        p[0] = func(**kwargs)

    wrapper.__doc__ = rule.format(pure_ply=True)

    return wrapper


def parse(defn, fname=None):
    "Takes a docstring and returns a parsed ruleset."

    if not defn:
        if fname is not None:
            raise NoDocstringError("Function %s has no docstring" % fname)
        else:
            raise NoDocstringError("Provided function has no docstring")

    return _parse(defn.strip())
    # defn = [line.strip() for line in defn.split('\n') if line.strip()]
    # return list(chain.from_iterable(_parse(line) for line in defn))


def process_function(func):
    """
      Takes a function with easyply defintion stored in the docstring and
      returns a dictionary of corresponding PLY-compatible functions.
    """

    ruleset = parse(func.__doc__, fname=func.__name__)
    expanded = expand_optionals(ruleset, format=False)

    ret = {}
    i = 0
    for rule in expanded:
        ret['p_%s_%s' % (func.__name__, i)] = create_wrapper(rule, func)
        i += 1
    return ret


class ObjectWrapper:
    def __init__(self, wrapped): self.wrapped = wrapped

    def __getitem__(self, key): return getattr(self.wrapped, key)

    def __setitem__(self, key, value): return setattr(self.wrapped, key, value)

    def items(self): return ((k, self[k]) for k in dir(self.wrapped))

    def __delitem__(self, key):
        return delattr(self.wrapped.__class__, key)


def get_rules(dictionary, prefix='px_'):
    return [(k, v) for k, v in dictionary.items() if k.startswith(prefix)]


def process_all(namespace, prefix='px_'):
    """
    Applies `process_function` to each function which name starts with `prefix`
    (`px_` by default). `process_all` accepts either a dictionary or a class
    and updates it with new functions.
    """

    if not isinstance(namespace, dict):
        namespace = ObjectWrapper(namespace)

    for f_name, func in get_rules(namespace, prefix):
        del namespace[f_name]
        for name, wrapper in process_function(func).items():
            namespace[name] = wrapper
