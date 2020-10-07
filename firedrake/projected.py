import ufl
from ufl.constantvalue import Zero
from ufl.core.ufl_type import ufl_type
from ufl.core.operator import Operator
from ufl.precedence import parstr
from firedrake.subspace import AbstractSubspace, Subspaces, ComplementSubspace, ScalarSubspace

from firedrake.ufl_expr import Argument


__all__ = ['Projected']


@ufl_type(num_ops=1, is_terminal_modifier=True, inherit_shape_from_operand=0, inherit_indices_from_operand=0)
class FiredrakeProjected(Operator):
    __slots__ = (
        "ufl_shape",
        "ufl_free_indices",
        "ufl_index_dimensions",
        "_subspace",
    )

    def __new__(cls, expression, subspace):
        if isinstance(expression, Zero):
            # Zero-simplify indexed Zero objects
            shape = expression.ufl_shape
            fi = expression.ufl_free_indices
            fid = expression.ufl_index_dimensions
            return Zero(shape=shape, free_indices=fi, index_dimensions=fid)
        else:
            return Operator.__new__(cls)

    def __init__(self, expression, subspace):
        # Store operands
        Operator.__init__(self, (expression, ))
        self._subspace = subspace

    def ufl_element(self):
        "Shortcut to get the finite element of the function space of the operand."
        return self.ufl_operands[0].ufl_element()

    def subspace(self):
        return self._subspace

    def _ufl_expr_reconstruct_(self, expression):
        return self._ufl_class_(expression, self.subspace())

    def __eq__(self, other):
        if self is other:
            return True
        elif not isinstance(other, FiredrakeProjected):
            return False
        else:
            return self.ufl_operands[0] == other.ufl_operands[0] and \
                   self.subspace() == other.subspace()

    def __repr__(self):
        return "%s(%s, %s)" % (self._ufl_class_.__name__, repr(self.ufl_operands[0]), repr(self.subspace()))

    def __str__(self):
        return "%s[%s]" % (parstr(self.ufl_operands[0], self),
                           self._subspace)


def Projected(form_argument, subspace):
    """Return `FiredrakeProjected` objects."""
    if isinstance(subspace, ComplementSubspace):
        return form_argument - Projected(form_argument, subspace.complement)
    if isinstance(subspace, (list, tuple)):
        subspace = Subspaces(*subspace)
    if isinstance(subspace, Subspaces):
        ms = tuple(Projected(form_argument, s) for s in subspace)
        return functools.reduce(lambda a, b: a + b, ms)
    elif isinstance(subspace, (AbstractSubspace, ufl.classes.ListTensor)):
        #TODO: ufl.classes.ListTensor can be removed if we trest splitting appropriately.
        return FiredrakeProjected(form_argument, subspace)
    else:
        raise TypeError("Must be `AbstractSubspace`, `Subspaces`, list, or tuple, not %s." % subspace.__class__.__name__)


from ufl.classes import FormArgument
from ufl.corealg.multifunction import MultiFunction
from ufl.corealg.map_dag import map_expr_dag
from ufl.algorithms.map_integrands import map_integrand_dags

from ufl.algorithms.traversal import iter_expressions
from ufl.corealg.traversal import unique_pre_traversal

class ExtractProjectedSubBlock(MultiFunction):
    def __init__(self):
        MultiFunction.__init__(self)

    def terminal(self, o):
        return o

    def argument(self, o):
        if self.subspaces[o.number()] is None:
            return o
        else:
            shape = o.ufl_shape
            fi = o.ufl_free_indices
            fid = o.ufl_index_dimensions
            return Zero(shape=shape, free_indices=fi, index_dimensions=fid)

    expr = MultiFunction.reuse_if_untouched

    def firedrake_projected(self, o, A):
        a = o.ufl_operands[0]
        if o.subspace() == self.subspaces[a.number()]:
            return o.ufl_operands[0]
        else:
            shape = o.ufl_shape
            fi = o.ufl_free_indices
            fid = o.ufl_index_dimensions
            return Zero(shape=shape, free_indices=fi, index_dimensions=fid)

    def split(self, form, subspaces):
        """Split a sub-form according to test/trial subspaces.

        :arg form: the sub-form to split.
        :arg subspaces: subspaces of test and trial spaces to extract.
            This should be 0-, 1-, or 2-tuple (whose length is the
            same as the number of arguments as the ``form``). The
            tuple can contain `None`s for extraction of non-projected
            arguments.

        Returns a new :class:`ufl.classes.Form` on the selected subspace.
        """
        args = form.arguments()
        if len(subspaces) != len(args):
            raise ValueError("Length of subspaces and arguments must match.")
        if len(args) == 0:
            return form
        self.subspaces = subspaces
        f = map_integrand_dags(self, form)
        return f


def extract_subspaces(a, number=None):
    if number:
        subspaces = set(o.subspace() for e in iter_expressions(a)
                        for o in unique_pre_traversal(e)
                        if isinstance(o, FiredrakeProjected) and isinstance(o.ufl_operands[0], Argument) and o.ufl_operands[0].number() == number)
    else:
        subspaces = set(o.subspace() for e in iter_expressions(a)
                        for o in unique_pre_traversal(e)
                        if isinstance(o, FiredrakeProjected))
    return tuple(sorted(subspaces, key=lambda x: x.count()))
    
