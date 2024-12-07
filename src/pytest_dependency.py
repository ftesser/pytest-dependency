"""$DOC"""

__version__ = "$VERSION"

import logging
from pathlib import Path

import py
import pytest
from _pytest.mark import ParameterSet
from _pytest.python import Module

logger = logging.getLogger(__name__)

_automark = False
_ignore_unknown = False


class DependencyItemStatus(object):
    """Status of a test item in a dependency manager.
    """

    Phases = ('setup', 'call', 'teardown')

    def __init__(self):
        self.results = { w:None for w in self.Phases }

    def __str__(self):
        l = ["%s: %s" % (w, self.results[w]) for w in self.Phases]
        return "Status(%s)" % ", ".join(l)

    def addResult(self, rep):
        self.results[rep.when] = rep.outcome

    def isSuccess(self):
        return list(self.results.values()) == ['passed', 'passed', 'passed']


class DependencyManager(object):
    """Dependency manager, stores the results of tests.
    """

    ScopeCls = {
        'session': pytest.Session,
        'package': pytest.Package,
        'module': pytest.Module,
        'class': pytest.Class,
    }

    @classmethod
    def getManager(cls, item, scope):
        """Get the DependencyManager object from the node at scope level.
        Create it, if not yet present.
        """
        node = item.getparent(cls.ScopeCls[scope])
        if not node:
            return None
        if not hasattr(node, 'dependencyManager'):
            node.dependencyManager = cls(scope)
        return node.dependencyManager

    def __init__(self, scope):
        self.results = {}
        self.scope = scope

    def addResult(self, item, name, rep):
        if not name:
            # Old versions of pytest used to add an extra "::()" to
            # the node ids of class methods to denote the class
            # instance.  This has been removed in pytest 4.0.0.
            nodeid = item.nodeid.replace("::()::", "::")
            if self.scope == 'session' or self.scope == 'package':
                name = nodeid
            elif self.scope == 'module':
                name = nodeid.split("::", 1)[1]
            elif self.scope == 'class':
                name = nodeid.split("::", 2)[2]
            else:
                raise RuntimeError("Internal error: invalid scope '%s'"
                                   % self.scope)
        status = self.results.setdefault(name, DependencyItemStatus())
        logger.debug("register %s %s %s in %s scope",
                     rep.when, name, rep.outcome, self.scope)
        status.addResult(rep)

    def checkDepend(self, depends, item):
        logger.debug("check dependencies of %s in %s scope ...",
                     item.name, self.scope)
        for i in depends:
            if i in self.results:
                if self.results[i].isSuccess():
                    logger.debug("... %s succeeded", i)
                    continue
                else:
                    logger.debug("... %s has not succeeded", i)
            else:
                logger.debug("... %s is unknown", i)
                if _ignore_unknown:
                    continue
            logger.info("skip %s because it depends on %s", item.name, i)
            pytest.skip("%s depends on %s" % (item.name, i))


def depends(request, other, scope='module'):
    """Add dependency on other test.

    Call pytest.skip() unless a successful outcome of all of the tests in
    other has been registered previously.  This has the same effect as
    the `depends` keyword argument to the :func:`pytest.mark.dependency`
    marker.  In contrast to the marker, this function may be called at
    runtime during a test.

    :param request: the value of the `request` pytest fixture related
        to the current test.
    :param other: dependencies, a list of names of tests that this
        test depends on.  The names of the dependencies must be
        adapted to the scope.
    :type other: iterable of :class:`str`
    :param scope: the scope to search for the dependencies.  Must be
        either `'session'`, `'package'`, `'module'`, or `'class'`.
    :type scope: :class:`str`

    .. versionadded:: 0.2

    .. versionchanged:: 0.5.0
        the scope parameter has been added.
    """
    item = request.node
    manager = DependencyManager.getManager(item, scope=scope)
    manager.checkDepend(other, item)


def pytest_addoption(parser):
    parser.addini("automark_dependency", 
                  "Add the dependency marker to all tests automatically", 
                  type="bool", default=False)
    parser.addini("collect_dependencies",
                  "Collect the dependent' tests",
                  type="bool", default=True)
    parser.addoption("--ignore-unknown-dependency",
                     action="store_true", default=False, 
                     help="ignore dependencies whose outcome is not known")


def pytest_configure(config):
    global _automark, _ignore_unknown
    _automark = config.getini("automark_dependency")
    _ignore_unknown = config.getoption("--ignore-unknown-dependency")
    config.addinivalue_line("markers", 
                            "dependency(name=None, depends=[]): "
                            "mark a test to be used as a dependency for "
                            "other tests or to depend on other tests.")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Store the test outcome if this item is marked "dependency".
    """
    outcome = yield
    marker = item.get_closest_marker("dependency")
    if marker is not None or _automark:
        rep = outcome.get_result()
        name = marker.kwargs.get('name') if marker is not None else None
        for scope in DependencyManager.ScopeCls:
            manager = DependencyManager.getManager(item, scope=scope)
            if (manager):
                manager.addResult(item, name, rep)


def pytest_runtest_setup(item):
    """Check dependencies if this item is marked "dependency".
    Skip if any of the dependencies has not been run successfully.
    """
    marker = item.get_closest_marker("dependency")
    if marker is not None:
        depends = marker.kwargs.get('depends')
        if depends:
            scope = marker.kwargs.get('scope', 'module')
            manager = DependencyManager.getManager(item, scope=scope)
            manager.checkDepend(depends, item)


def collect_dependencies(config, item, items):
    marker_list = list()
    dependencies = list()
    markers = item.own_markers
    for root_marker in markers:
        if root_marker.name == 'dependency':
            marker_list.append(root_marker)
        elif root_marker.name == 'parametrize':
            append_parametrized_dependency_markers(root_marker, marker_list)

    for marker in marker_list:
        depends = marker.kwargs.get('depends')
        scope = marker.kwargs.get('scope')
        if marker.name == 'dependency' and depends:
            for depend in depends:
                if scope == 'session' or scope == 'package':
                    depend_module, depend_func = depend.split("::", 1)
                    depend_path = py.path.local(Path(config.rootdir) / Path(depend_module))
                    depend_parent = Module.from_parent(item.parent, fspath=depend_path)
                    depend_nodeid = depend
                else:
                    if item.cls:
                        # class cases
                        current_class_name = item.cls.__name__
                        if "::" not in depend or "{}::".format(current_class_name) in depend:
                            # the first condition (depend does not contain ::) means that is a "mark.dependency name" or it is in the same class
                            # the second condition means that test method depends on another test method in the same class
                            depend_func = depend.split("::")[-1]
                            depend_parent = item.parent
                        else:
                            # test method depends on a test method in another class
                            depend_func = depend.split("::")[-1]
                            module = item.parent.parent
                            for cl in module.collect():
                                if cl.cls and cl.cls.__name__ == depend.split("::")[0]:
                                    depend_parent = cl
                                    break
                    else:
                        depend_func = depend
                        depend_parent = item.parent
                    depend_nodeid = '{}::{}'.format(depend_parent.nodeid, depend_func)
                    # assert depend_nodeid == depend_nodeid2
                # class example: depend_func = test_b; depend_nodeid = test_class.py::TestClass::test_b; depend_parent = <Class Tests>
                dependencies.append((depend_func, depend_nodeid, depend_parent))

        for depend_func, depend_nodeid, depend_parent in dependencies:
            # first look if depend_nodeid is already inside the list of items
            # this solution use a double list with the two conventions of nodeid (with the real function name and with the name of dependency mark name)
            # in the future should be better to normalize (using just one convention) the depend_nodeid before to compare
            list_of_items_nodeid = [item_i.nodeid for item_i in items] # nodeid with the real function name
            list_of_items_nodeid_name = get_list_of_nodeid_with_dependency_mark_name(items) # nodeid with the name of dependency mark name
            full_list_of_items_nodeid = list_of_items_nodeid + list_of_items_nodeid_name
            if depend_nodeid not in full_list_of_items_nodeid:
                found = False
                # first look if depend_func is the real name of a test function
                item_to_add = get_dep_function(depend_func, depend_parent)
                if item_to_add is not None:
                    found = True
                else:
                    logger.warning("collect_dependencies: the test function {}::{} does not exist".format(depend_parent, depend_func))
                    # if not, look if depend_func is in the mark.dependency name
                    for item_j in item.parent.collect():
                        if found:
                            logger.info("The test function {} is in the mark.dependency name".format(depend_func))
                            break
                        for marker in item_j.own_markers:
                            if marker.name == 'dependency' and marker.kwargs.get('name') == depend_func:
                                item_to_add = item_j
                                found = True
                                break
                if found:
                    items.insert(0, item_to_add)
                    # recursive look for dependencies into item_to_add
                    collect_dependencies(config, item_to_add, items)
    return

def append_parametrized_dependency_markers(root_marker, marker_list):
    for arg in root_marker.args:
        if isinstance(arg, list):
            for param in arg:
                if isinstance(param, ParameterSet):
                    if isinstance(param.marks, tuple):
                        for mark in param.marks:
                            if mark.name == 'dependency':
                                marker_list.append(mark)

def get_dep_function(depend_func, depend_parent):
    for item in depend_parent.collect():
        if item.name == depend_func:
            return item


def get_list_of_nodeid_with_dependency_mark_name(items):
    list_of_nodeid = []
    for item in items:
        markers = item.own_markers
        for marker in markers:
            if marker.name == 'dependency':
                name = marker.kwargs.get('name')
                if name:
                    node_id_split_list = item.nodeid.split("::")
                    node_id_split_list[-1] = name
                    # reconstruct the nodeid with the name of dependency mark name
                    nodeid = "::".join(node_id_split_list)
                    list_of_nodeid.append(nodeid)
    return list_of_nodeid


def pytest_collection_modifyitems(config, items):
    if config.getini('collect_dependencies'):
        for item in items:
            collect_dependencies(config, item, items)
