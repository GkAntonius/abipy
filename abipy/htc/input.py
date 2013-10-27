"""
This module defines objects that faciliate the creation of the 
ABINIT input files. The syntax is similar to the one used 
in ABINIT with small differences. 
"""
from __future__ import print_function, division

import os
import collections
import warnings
import itertools
import copy
import abc
import numpy as np

from pymatgen.io.abinitio.pseudos import PseudoTable
from pymatgen.io.abinitio.strategies import select_pseudos
from abipy.core import Structure
from abipy.tools import is_string, list_strings

__all__ = [
    "AbiInput",
    "LdauParams",
    "LexxParams",
]

# Variables that must have a unique value throughout all the datasets.
_ABINIT_NO_MULTI = [
    "jdtset",
    "ndtset",
    "ntypat",
    "znucl",
    "cpus",
    "cpum",
    "cpuh",
    "npsp",
    "timopt",
    "iatcon",
    "natcon",
    "nconeq",
    "prtxtypat",
    "wtatcon",
]


def straceback():
    """Returns a string with the traceback."""
    import traceback
    return traceback.format_exc()


class Input(object): 
    """
    Base class foor Input objects.

    An input object must define have a make_input method 
    that returns the string representation used by the client code.
    """
    __metaclass__ = abc.ABCMeta

    def copy(self):
        """Shallow copy of the input."""
        return copy.copy(self)
                                   
    def deepcopy(self):
        """Deep copy of the input."""
        return copy.deepcopy(self)

    def write(self, filepath):
        """
        Write the input file to file. Returns a string with the input.
        """
        dirname = os.path.dirname(filepath)
        if not os.path.exists(dirname): 
            os.makedirs(dirname)
                                                                                      
        # Write the input file.
        #input_string = str(self)
        input_string = self.make_input()
        with open(filepath, "w") as fh:
           fh.write(input_string)

        return input_string

    #@abc.abstractmethod
    #def make_input(self)

    #@abc.abstractproperty
    #def structure(self):

    #def set_structure(self, structure):

    #def set_variables(self, dtset=0, **vars):
    #    """
    #    Set the value of a set of input variables.

    #    Args:
    #        dtset:
    #            Int with the index of the dataset, slice object of iterable 
    #        vars:
    #            Dictionary with the variables.
    #    """
    #    for idt in self._dtset2range(dtset):
    #        self[idt].set_variables(**vars)

    #def remove_variables(self, keys, dtset=0):
    #    """
    #    Remove the variable listed in keys
    #                                                                         
    #    Args:
    #        dtset:
    #            Int with the index of the dataset, slice object of iterable 
    #        keys:
    #            List of variables to remove.
    #    """
    #    for idt in self._dtset2range(dtset):
    #        self[idt].remove_variables(keys)



class AbinitInputError(Exception):
    """Base error class for exceptions raised by `AbiInput`"""


class AbiInput(Input):
    """
    This object represents an ABINIT input file. It supports multi-datasets a
    and provides an easy-to-use interface for defining the variables of the calculation.
    """
    Error = AbinitInputError

    def __init__(self, pseudos, pseudo_dir="", ndtset=1, comment=""):
        """
        Args:
            pseudos:
                String or list of string with the name of the pseudopotential files.
            pseudo_dir:
                Name of the directory where the pseudopotential files are located.
            ndtset:
                Number of datasets.
            comment:
                Optional string with a comment that will be placed at the beginning of the file.
        """
        # Dataset[0] contains the global variables common to the different datasets
        # Dataset[1:ndtset+1] stores the variables specific to the different datasets.
        self._ndtset = ndtset

        self._datasets = []
        for i in range(ndtset+1):
            dt0 = None
            if i > 0: dt0 = self._datasets[0]
            self._datasets.append(Dataset(index=i, dt0=dt0))

        self._datasets[0]["ndtset"] = ndtset

        # Setup of the pseudopotential files.
        if isinstance(pseudos, PseudoTable):
            self._pseudos = pseudos

        else:
            # String(s)
            pseudo_dir = os.path.abspath(pseudo_dir)

            pseudo_paths = [os.path.join(pseudo_dir, p) for p in list_strings(pseudos)]

            missing = [p for p in pseudo_paths if not os.path.exists(p)]
            if missing:
                raise self.Error("Cannot find the following pseudopotential files:\n%s" % str(missing)) 

            try:
                self._pseudos = PseudoTable(pseudo_paths)

            except Exception as exc:
                msg = "\nIgnoring error raised while parsing pseudopotential files:\n Backtrace:" + straceback()
                warnings.warn(msg)
                self._pseudos = []

        if comment:
            self.set_comment(comment)

    #def make_input(self):
    #    return str(self)

    def __str__(self):
        """String representation i.e. the input file read by Abinit."""
        if self.ndtset > 1:
            s = ""
            for (i, dataset) in enumerate(self):
                header = "### DATASET %d ###" % i
                if i == 0: 
                    header = "### GLOBAL VARIABLES ###"

                str_dataset = str(dataset)
                if str_dataset:
                    header = len(header) * "#" + "\n" + header + "\n" + len(header) * "#" + "\n"
                    s += "\n" + header + str(dataset) + "\n"
        else:
            # single datasets ==> don't append the dataset index to the variables in self[1]
            # this trick is needed because Abinit complains if ndtset is not specified 
            # and we have variables that end with the dataset index e.g. acell1
            # We don't want to specify ndtset here since abinit will start to add DS# to 
            # the input and output files thus complicating the algorithms we have to use
            # to locate the files.
            d = self[0].deepcopy()
            d.update(self[1])
            s = d.to_string(post="")

        return s

    def __getitem__(self, key):
        return self._datasets[key]

    def __setattr__(self, varname, value):
        if varname.startswith("ndtset"):
            raise self.Error("Cannot change read-only variable ndtset")

        if varname.startswith("_"):
            # Standard behaviour for "private" variables.
            super(AbiInput, self).__setattr__(varname, value)

        else:
            if not varname[-1].isdigit():
                # Global variable.
                self[0].set_variable(varname, value)

            else:
                # Find the index of the dataset.
                idt = ""
                for i, c in enumerate(reversed(varname)):
                    if c.isdigit():
                        idt += c
                    else:
                        break

                idt = int("".join(reversed(idt)))
                if not (self.ndtset >= idt  >= 1):
                    raise self.Error("Invalid dataset index %d, ndtset %d " % (idt, self.ndtset))

                # Strip the numeric index.
                varname = varname[:len(varname)-i]

                self[idt].set_variable(varname, value)

                # Handle no_multi variables.
                if varname in _ABINIT_NO_MULTI:

                    if varname in self[0]:
                        glob_value = np.array(self[0][varname])
                        isok  = np.all(glob_value == np.array(value))
                        if not isok:
                            err_msg = "NO_MULTI variable: dataset 0: %s, dataset %d: %s" % (str(glob_value), idt, str(value))
                            raise self.Error(err_msg)
                    else:
                        self[0].set_variable(varname, value)

    @property
    def ndtset(self):
        """Number of datasets."""
        return self[0]["ndtset"]

    @property
    def pseudos(self):
        """List of `Pseudo` objecst."""
        return self._pseudos

    @property
    def structure(self):
        """
        Returns the `Structure` associated to the ABINIT input.

        Raises:
            ValueError if we have multi datasets with different 
            structure so that users will learn that multiple datasets are bad.
        """
        structures = [dt.structure for dt in self[1:]]

        if all(s == structures[0] for s in structures):
            return structures[0]

        raise ValueError("Cannot extract a unique structure from an input file with multiple datasets!\n" + 
                         "Please DON'T use multiple datasets with different unit cells!")

    @staticmethod
    def _dtset2range(dtset):
        """
        Helper function to convert dtset into a range. Accepts int, slice objects or iterable.
        """
        if isinstance(dtset, int):
            return [dtset]

        elif isinstance(dtset, slice): 
            start = dtset.start if dtset.start is not None else 0
            stop = dtset.stop
            step = dtset.step if dtset.step is not None else 1
            return range(start, stop, step)

        elif isinstance(dtset, collections.Iterable):
            return dtset

        raise self.Error("Don't know how to convert %s to a range-like object" % str(dtset))

    def split_datasets(self):
        """
        Split an input file with multiple datasets into a  list of `ndtset` distinct input files.
        """
        # Propagate subclasses (if any)
        cls = self.__class__ 
        news = []

        for i in range(self.ndtset):
            my_vars = self[i+1].allvars
            my_vars.pop("ndtset", None)

            # Cannot use get*, ird* variables since links must be explicit.
            for varname in my_vars:
                if varname.startswith("get") or varname.startswith("ird"):
                    err_msg = ("get* or ird* variables should not be present in the input when you split it into datasets")
                    raise ValueError(err_msg)

            new = cls(pseudos=self.pseudos, ndtset=1)
            new.set_variables(**my_vars)
            news.append(new)
    
        return news

    def set_variables(self, dtset=0, **vars):
        """
        Set the value of a set of input variables.

        Args:
            dtset:
                Int with the index of the dataset, slice object of iterable 
            vars:
                Dictionary with the variables.
        """
        for idt in self._dtset2range(dtset):
            self[idt].set_variables(**vars)

    def remove_variables(self, keys, dtset=0):
        """
        Remove the variable listed in keys
                                                                             
        Args:
            dtset:
                Int with the index of the dataset, slice object of iterable 
            keys:
                List of variables to remove.
        """
        for idt in self._dtset2range(dtset):
            self[idt].remove_variables(keys)

    def list_variable(self, varname):
        # Global value
        glob = self[0].get(varname, None)
        # Values defined in the datasets.
        vals = [self[idt].get(varname, None) for idt in range(1,self.ndtset+1)]
        
        # Replace None with glob.
        values = []
        for v in vals:
            if v is not None:
                values.append(v)
            else:
                values.append(glob)

        return values

    def set_comment(self, comment, dtset=0):
        """Set the main comment in the input file."""
        for idt in self._dtset2range(dtset):
            self[idt].set_comment(comment)

    def linspace(self, varname, start, stop, endpoint=True):
        """
        Returns `ndtset` evenly spaced samples, calculated over the interval [`start`, `stop`].

        The endpoint of the interval can optionally be excluded.

        Args:
            start: 
                The starting value of the sequence.
            stop:
                The end value of the sequence, unless `endpoint` is set to False.
                In that case, the sequence consists of all but the last of ``ndtset + 1``
                evenly spaced samples, so that `stop` is excluded.  Note that the step
                size changes when `endpoint` is False.
        """
        if varname in self[0]:
            raise self.Error("varname %s is already defined in globals" % varname)
            
        lspace = np.linspace(start, stop, num=self.ndtset, endpoint=endpoint, retstep=False)

        for (dataset, value) in zip(self[1:], lspace):
            dataset.set_variable(varname, value)

    def arange(self, varname, start, stop, step):
        """
        Return evenly spaced values within a given interval.

        Values are generated within the half-open interval ``[start, stop)``
        (in other words, the interval including `start` but excluding `stop`).

        When using a non-integer step, such as 0.1, the results will often not
        be consistent.  It is better to use ``linspace`` for these cases.

        Args:
            start: 
                Start of interval.  The interval includes this value. The default start value is 0.
            stop:
                End of interval.  The interval does not include this value, except
                in some cases where `step` is not an integer and floating point
            step: 
                Spacing between values.  For any output `out`, this is the distance
                between two adjacent values, ``out[i+1] - out[i]``.  The default
                step size is 1.  If `step` is specified, `start` must also be given.
        """
        if varname in self[0]:
            raise self.Error("varname %s is already defined in globals" % varname)

        arang = np.arange(start=start, stop=stop, step=step)
        if len(arang) != self.ndtset:
            raise self.Error("len(arang) %d != ndtset %d" % (len(arang), self.ndtset))

        for (dataset, value) in zip(self[1:], arang):
            dataset.set_variable(varname, value)

    def product(self, *items):
        """
        Cartesian product of input iterables.  Equivalent to nested for-loops.

        .. example:

            inp.product("tsmear", "ngkpt", [[2,2,2], [4,4,4]], [0.1, 0.2, 0.3])
        """
        # Split items into varnames and values
        for i, item in enumerate(items):
            if not is_string(item):
                break

        varnames, values = items[:i], items[i:]
        if len(varnames) != len(values):
            raise self.Error("The number of variables must equal the number of lists")

        varnames = [ [varnames[i]] * len(values[i]) for i in range(len(values))]
        varnames = itertools.product(*varnames)
        values = itertools.product(*values)

        idt = 0
        for names, values in zip(varnames, values):
            idt += 1
            self[idt].set_variables(**{k:v for k, v in zip(names, values)})
        
        if idt != self.ndtset:
            raise self.Error("The number of configurations must equal ndtset while %d != %d" % (idt, self.ndtset))

    def set_structure(self, structure, dtset=0):
        """Set the `Structure` object for the specified dtset."""
        for idt in self._dtset2range(dtset):
            self[idt].set_structure(structure)

    def set_structure_from_file(self, filepath, dtset=0):
        """Set the `Structure` object for the specified dtset (data is read from filepath)."""
        structure = Structure.from_file(filepath)
        self.set_structure(structure, dtset=dtset)
        return structure

    def set_kmesh(self, ngkpt, shiftk, kptopt=1, dtset=0):
        """
        Set the variables defining the k-point sampling for the specified dtset.
        """
        for idt in self._dtset2range(dtset):
            self[idt].set_kmesh(ngkpt, shiftk, kptopt=kptopt)

    def set_kpath(self, ndivsm, kptbounds=None, iscf=-2, dtset=0):
        """
        Set the variables defining the k-path for the specified dtset.

        The list of K-points is taken from the pymatgen database if kptbounds is None

        Args:
            ndivsm:
                Number of divisions for the smallest segment.
            kptbounds:
                k-points defining the path in k-space.
            iscf:
                iscf variable.
            dtset:
                Index of the dataset. 0 for global variables.
        """
        for idt in self._dtset2range(dtset):
            self[idt].set_kpath(ndivsm, kptbounds=kptbounds, iscf=iscf)

    def set_kptgw(self, kptgw, bdgw, dtset=0):
        """
        Set the variables defining the k point for the GW corrections
        """
        for idt in self._dtset2range(dtset):
            self[idt].set_kptgw(kptgw, bdgw)

_UNITS = {
    'bohr' : 1.0,
    'angstrom' : 1.8897261328856432,
    'hartree' : 1.0,
    'Ha' : 1.0,
    'eV' : 0.03674932539796232,
}


# TODO this should be the "actual" input file!
class Dataset(collections.Mapping):
    """
    This object stores the ABINIT variables for a single dataset.
    """
    Error = AbinitInputError

    def __init__(self, index, dt0, *args, **kwargs):
        self.vars = collections.OrderedDict(*args, **kwargs)
        self._index = index
        self._dt0 = dt0

    def __repr__(self):
        "<%s at %s>" % self.__class__.__name__, id(self)

    def __str__(self):
        return self.to_string()

    def __len__(self):
        return self.vars

    def __iter__(self):
        return self.vars.__iter__()

    def __getitem__(self, key):
        return self.vars[key]

    def __setitem__(self, key, value):
        self.vars[key] = value

    def __contains__(self, key):
        return key in self.vars

    def deepcopy(self):
        """Deepcopy of the `Dataset`"""
        return copy.deepcopy(self)

    def keys(self):
        return self.vars.keys()

    def items(self):
        return self.vars.items()

    def get(self, value, default=None):
        try:
            return self[value]
        except KeyError:
            return default

    def pop(self, k, *d):
        """
        D.pop(k[,d]) -> v, remove specified key and return the corresponding value.
        If key is not found, d is returned if given, otherwise KeyError is raised
        """
        if d:
            return self.vars.pop(k, d[0])
        else:
            return self.vars.pop(k)

    def update(self, e, **f):
        """
        D.update([E, ]**F) -> None.  Update D from dict/iterable E and F.
        If E present and has a .keys() method, does:     for k in E: D[k] = E[k]
        If E present and lacks .keys() method, does:     for (k, v) in E: D[k] = v
        In either case, this is followed by: for k in F: D[k] = F[k]
        """
        self.vars.update(e, **f)

    @property
    def index(self):
        """The index of the dataset within the input."""
        return self._index

    @property
    def dt0(self):
        return self._dt0

    @property
    def global_vars(self):
        """Copy of the dictionary with the global variables."""
        return self.dt0.vars.copy()

    @property
    def allvars(self):
        """
        Dictionay with the variables of the dataset + the global variables.
        Variables local to the dataset overwrite the global values (if any).
        """
        all_vars = self.global_vars
        all_vars.update(self.vars)
        return all_vars.copy()

    def to_string(self, sortmode=None, post=None):
        """
        String representation.

        Args:
            sortmode:
                Not available
            post:
                String that will be appended to the name of the variables
                Note that post is usually autodetected when we have multiple datatasets
                It is mainly used when we have an input file with a single dataset
                so that we can prevent the code from adding "1" to the name of the variables 
                (In this case, indeed, Abinit complains if ndtset=1 is not specified 
                and we don't want ndtset=1 simply because the code will start to add 
                _DS1_ to all the input and output files.
        """
        lines = []
        app = lines.append

        if self.comment:
            app("# " + self.comment.replace("\n", "\n#"))

        if post is None:
            post = "" if self.index == 0 else str(self.index)
        else:
            post = post

        if sortmode is None:
            # no sorting.
            keys = self.keys()
        elif sortmode is "a":
            # alphabetical order.
            keys = sorted(self.keys())
        #elif sortmode is "t": TODO
            # group variables by topic
        else:
            raise ValueError("Unsupported value for sortmode %s" % str(sortmode))

        for var in keys:
            value = self[var]
            # Do not print NO_MULTI variables except for dataset 0.
            if self.index != 0 and var in _ABINIT_NO_MULTI:
                continue

            # Print ndtset only if we really have datasets. 
            # This trick prevents abinit from adding DS# to the output files.
            # thus complicating the creation of workflows made of separated calculations.
            if var == "ndtset" and value == 1:
                continue

            varname = var + post
            app("%s %s" % (varname, format_var(var, value)))

        return "\n".join(lines)

    @property
    def comment(self):
        try:
            return self._comment

        except AttributeError:
            return None

    def set_comment(self, comment):
        """Set a comment to be included at the top of the file."""
        self._comment = comment

    def set_variable(self, varname, value):
        """Set a single variable."""
        if varname in self:

            try: 
                iseq = (self[varname] == value)
                iseq = np.all(iseq)
            except ValueError:
                # array like.
                iseq = np.allclose(self[varname], value)
            except:
                iseq = False

            if not iseq:
                msg = "%s is already defined with a different value:\n old: %s, new %s" % (varname, str(self[varname]), str(value))
                warnings.warn(msg)

        self[varname] = value

        # Handle no_multi variables.
        if varname in _ABINIT_NO_MULTI and self.index != 0:
                                                                                                                      
            if varname in self.dt0:
                glob_value = np.array(self.dt0[varname])
                isok  = np.all(glob_value == np.array(value))
                if not isok:
                    err_msg = "NO_MULTI variable: dataset 0: %s, dataset %d: %s" % (str(glob_value), self.index, str(value))
                    raise self.Error(err_msg)
            else:
                self.dt0.set_variable(varname, value)

    def set_variables(self, **vars):
        """Set the value of the variables provied in the dictionary **vars"""
        for (varname, varvalue) in vars.items():
            self.set_variable(varname, varvalue)

    def remove_variables(self, keys):
        """Remove the variables listed in keys."""
        for key in list_strings(keys):
            self.pop(key)
            #self.pop(key, None)

    @property
    def structure(self):
        """Returns the `Structure` associated to this dataset."""
        try:
            return self._structure

        except AttributeError:
            structure = Structure.from_abivars(self.allvars)

            self.set_structure(structure)
            return self._structure

    def set_structure(self, structure):
        if hasattr(self, "_structure") and self._structure != structure:
            raise self.Error("Dataset object already has a structure object, cannot overwrite")

        self._structure = structure
        if structure is None:
            return

        self.set_variables(**structure.to_abivars())

    # Helper functions to facilitate the specification of several variables.
    def set_kmesh(self, ngkpt, shiftk, kptopt=1):
        """
        Set the variables for the sampling of the BZ.

        Args:
            ngkpt:
                Monkhorst-Pack divisions
            shiftk:
                List of shifts.
            kptopt:
                Option for the generation of the mesh.
        """
        shiftk = np.reshape(shiftk, (-1,3))
        
        self.set_variables(ngkpt=ngkpt,
                           kptopt=kptopt,
                           nshiftk=len(shiftk),
                           shiftk=shiftk,
                           )

    def set_kpath(self, ndivsm, kptbounds=None, iscf=-2):
        """
        Set the variables for the computation of the band structure.

        Args:
            ndivsm:
                Number of divisions for the smallest segment.
            kptbounds
                k-points defining the path in k-space.
        """
        if kptbounds is None:
            kptbounds = [k.frac_coords for k in self.structure.hsym_kpoints]

        kptbounds = np.reshape(kptbounds, (-1,3))

        self.set_variables(kptbounds=kptbounds,
                           kptopt=-(len(kptbounds)-1),
                           ndivsm=ndivsm,
                           iscf=iscf,
                           )

    def set_kptgw(self, kptgw, bdgw):
        """
        Set the variables (k-points, bands) for the computation of the GW corrections.

        Args
            kptgw:
                List of k-points in reduced coordinates.
            bdgw:
                Specifies the range of bands for the GW corrections.
                Accepts iterable that be reshaped to (nkptgw, 2) 
                or a tuple of two integers if the extrema are the same for each k-point.
        """
        kptgw = np.reshape(kptgw, (-1,3))
        nkptgw = len(kptgw)

        if len(bdgw) == 2:
            bdgw = len(kptgw) * bdgw

        self.set_variables(kptgw=kptgw,
                           nkptgw=nkptgw,
                           bdgw=np.reshape(bdgw, (nkptgw, 2)),
                           )


def format_var(varname, value):
    """
    Return a string for a single input variable to be written in the input file.
    Always ends with a carriage return.
    """
    if value is None or not str(value):
        return ""

    # By default, do not impose a number of decimal points ...but not for those
    digits = {
        ('xred','xcart','qpt','kpt') : 10,
        ('ngkpt','kptrlatt', 'ngqpt'): 0,
    }

    precision = {}
    for t, numd in digits.items():
        for varname in t:
            precision[varname] = numd 

    floatdecimal = precision.get(varname, 0)

    line = " "

    if isinstance(value, np.ndarray):
        n = 1
        for i in np.shape(value):
            n *= i
        value = list(np.reshape(value, n))

    if isinstance(value, (list, tuple)):
        # values in lists
        # Reshape a list of lists into a single list
        if all(isinstance(v, list) for v in value):
            line += format_list_of_list(value, floatdecimal)

        else:
            # Maximum number of values per line.
            valperline = 3
            if any(inp in varname for inp in ['bdgw']):
                valperline = 2

            line += format_list(value, valperline, floatdecimal)

    else:
        # scalar values
        line += ' ' + str(value)

    return line


def format_scalar(val, floatdecimal=0):
    """
    Format a single numerical value into a string
    with the appropriate number of decimals.
    """
    sval = str(val)
    if sval.isdigit() and floatdecimal == 0:
        return sval

    try:
        fval = float(val)
    except:
        return sval

    if fval == 0 or (abs(fval) > 1e-3 and abs(fval) < 1e4):
        form = 'f'
        addlen = 5
    else:
        form = 'e'
        addlen = 8

    ndec = max(len(str(fval-int(fval)))-2, floatdecimal)
    ndec = min(ndec, 10)

    sval = '{v:>{l}.{p}{f}}'.format(v=fval, l=ndec+addlen, p=ndec, f=form)

    return sval.replace('e', 'd')


def format_list_of_list(values, floatdecimal=0):
    """Format a list of lists."""

    lvals = flattens(values)

    # Determine the representation
    if all(isinstance(v, int) for v in lvals):
        type_all = int
    else:
        try:
            for v in lvals:
                float(v)
            type_all = float
        except:
            type_all = str

    # Determine the format
    width = max(len(str(s)) for s in lvals)
    if type_all == int:
        formatspec = '>{}d'.format(width)

    elif type_all == str:
        formatspec = '>{}'.format(width)

    else:
        # Number of decimal
        maxdec = max(len(str(f-int(f)))-2 for f in lvals)
        ndec = min(max(maxdec, floatdecimal), 10)

        if all(f == 0 or (abs(f) > 1e-3 and abs(f) < 1e4) for f in lvals):
            formatspec = '>{w}.{p}f'.format(w=ndec+5, p=ndec)
        else:
            formatspec = '>{w}.{p}e'.format(w=ndec+8, p=ndec)

    line = '\n'
    for L in values:
        for val in L:
            line += ' {v:{f}}'.format(v=val, f=formatspec)
        line += '\n'

    return line


def format_list(values, valperline=3, floatdecimal=0):
    """
    Format a list of values into a string.  The result might be spread among
    several lines, each line starting with a blank space.
    'valperline' specifies the number of values per line.
    """
    line = ""
    # Format the line declaring the value
    for i, val in enumerate(values):
        line += ' ' + format_scalar(val, floatdecimal)
        if (i+1) % valperline == 0:
            line += '\n'

    # Add a carriage return in case of several lines
    if '\n' in line.rstrip('\n'):
        line = '\n' + line

    # Add a carriage return at the end
    if not line.endswith('\n'):
        line += '\n'

    return line


def string_to_value(sval):
    """
    Interpret a string variable and attempt to return a value of the appropriate type.  
    If all else fails, return the initial string.
    """
    value = None
    try:
        for part in sval.split():
            if '*' in part:
                if part[0] == '*':
                    # cases like istwfk *1
                    value = None
                    break

                else:
                    # cases like acell 3*3.52
                    n = int(part.split('*')[0])
                    f = convert_number(part.split('*')[1])
                    if value is None:
                        value = []
                    value += n * [f]
                    continue

            if '/' in part:
                # Fractions
                (num, den) = (float(part.split('/')[i]) for i in range(2))
                part = num / den

            if part in _UNITS.keys():
                # Unit
                if value is None:
                    msg = "Could not apply the unit tolken '%s'." %(part)
                    warnings.warn(msg)
                elif isinstance(value, list):
                    value.append(part)
                else:
                    value = [value, part]

                # Convert
                if False:
                    if isinstance(value, (list, tuple)):
                        for i in range(len(value)):
                            value[i] *= _UNITS[part]
                    elif is_string(value):
                        value = None
                        break
                    else:
                        value *= _UNITS[part]

                continue

            # Convert
            try:
                val = convert_number(part)
            except:
                val = part

            if value is None:
                value = val
            elif isinstance(value, list):
                value.append(val)
            else:
                value = [value, val]
    except:
        value = None

    if value is None:
        value = sval

    return value


def format_variable_dict(variables):
    """Format a dictionary of input variables into a multi-line string."""
    s = ""
    for (var, val) in variables.items():
        s += format_var(var, val)

    return s


def flattens(lists):
    """Transform a list of lists into a single list."""
    if not isinstance(lists[0], list):
        return lists
    lst = []
    for l in lists:
        lst += l

    return lst


def listify(obj):
    """Transform any object, iterable or not, to a list."""
    if isinstance(obj, collections.Iterable):
        return obj

    elif isinstance(obj, collections.Iterator):
        return list(obj)

    else:
        return [obj]


def is_number(s):
    """Returns True if the argument can be converted to float."""
    try:
        float(s)
        return True
    except:
        return False


def convert_number(value):
    """
    Converts some object to a float or a string.
    If the argument is an integer or a float, returns the same object.
    If the argument is a string, tries to convert to an integer, then to a float.
    The string '1.0d-03' will be treated the same as '1.0e-03'
    """
    if isinstance(value (float, int)):
        return value

    elif is_string(value):

        if is_number(value):
            try:
                return int(value)
            except ValueError:
                return float(value)

        else:
            val = value.replace('d', 'e')
            if is_number(val):
                return float(val)
            else:
                raise ValueError("convert_number failed")

    else:
        raise ValueError("convert_number failed")


from collections import namedtuple
from pymatgen.core.units import Energy, EnergyArray

class LujForSpecie(namedtuple("LdauForSpecie", "l u j unit")):
    """
    This object stores the value of l, u, j used for a single atomic specie.
    """
    def __new__(cls, l, u, j, unit):
        """
        Args:
            l: 
                Angular momentum (int or string).
            u:
                U value
            j:
                J Value
            unit:
                Energy unit for u and j.
        """
        l = l
        u = Energy(u, unit)
        j = Energy(j, unit)
        return super(cls, LujForSpecie).__new__(cls, l, u, j, unit)


class LdauParams(object):
    """
    This object stores the parameters for LDA+U calculations with the PAW method
    It facilitates the specification of the U-J parameters in the Abinit input file.
    (see `to_abivars`). The U-J operator will be applied only on  the atomic species 
    that have been selected by calling `lui_for_symbol`.
    """
    def __init__(self, usepawu, structure):
        """
        Arg:
            usepawu:
                Abinit variable `usepawu` defining the LDA+U method.
            structure:
                `Structure` object.
        """
        self.usepawu = usepawu
        self.structure = structure
        self._params = {} 

    @property
    def symbols_by_typat(self):
        return [specie.symbol for specie in self.structure.types_of_specie]

    def luj_for_symbol(self, symbol, l, u, j, unit="eV"):
        """
        Args:
            symbol:
                Chemical symbol of the atoms on which LDA+U should be applied.
            l:
                Angular momentum.
            u: 
                Value of U.
            j:
                Value of J.
            unit:
                Energy unit of U and J.
        """
        if symbol not in self.symbols_by_typat:
            err_msg = "Symbol %s not in symbols_by_typat:\n%s" % (symbol, self.symbols_by_typat)
            raise ValueError(err_msg)

        if symbol in self._params:
            err_msg = "Symbol %s is already present in LdauParams! Cannot overwrite:\n" % symbol
            raise ValueError(err_msg)

        self._params[symbol] = LujForSpecie(l=l, u=u, j=j, unit=unit)

    def to_abivars(self):
        """
        Returns a dict with the Abinit variables.
        """
        lpawu, upawu, jpawu = [], [], []

        for symbol in self.symbols_by_typat:
            p = self._params.get(symbol, None)

            if p is not None:
                l, u, j = p.l, p.u.to("eV"), p.j.to("eV")
            else:
                l, u, j = -1, 0, 0

            lpawu.append(int(l)) 
            upawu.append(float(u))
            jpawu.append(float(j))

        # convert upawu and jpaw to string so that we can use 
        # eV unit in the Abinit input file (much more readable).
        return dict(
            usepawu=self.usepawu,
            lpawu=" ".join(map(str, lpawu)),
            upawu=" ".join(map(str, upawu))  + " eV",
            jpawu=" ".join(map(str, jpawu)) + " eV",
        )


class LexxParams(object):
    """
    This object stores the parameters for local exact exchange calculations with the PAW method
    It facilitates the specification of the LEXX parameters in the Abinit input file.
    (see `to_abivars`). The LEXX operator will be applied only on the atomic species 
    that have been selected by calling `lexx_for_symbol`.
    """
    def __init__(self, structure):
        """
        Arg:
            structure:
                `Structure` object.
        """
        self.structure = structure
        self._lexx_for_symbol = {} 

    @property
    def symbols_by_typat(self):
        return [specie.symbol for specie in self.structure.types_of_specie]

    def lexx_for_symbol(self, symbol, l):
        """
        Enable LEXX for the given chemical symbol and the angular momentum l 

        Args:
            symbol:
                Chemical symbol of the atoms on which LEXX should be applied.
            l:
                Angular momentum.
        """
        if symbol not in self.symbols_by_typat:
            err_msg = "Symbol %s not in symbols_by_typat:\n%s" % (symbol, self.symbols_by_typat)
            raise ValueError(err_msg)

        if symbol in self._lexx_for_symbol:
            err_msg = "Symbol %s is already present in LdauParams! Cannot overwrite:\n" % symbol
            raise ValueError(err_msg)

        self._lexx_for_symbol[symbol] = l

    def to_abivars(self):
        """
        Returns a dict with the Abinit variables.
        """
        lexx_typat = []

        for symbol in self.symbols_by_typat:
            l = self._lexx_for_symbol.get(symbol, -1)
            lexx_typat.append(int(l)) 

        return dict(
            useexexch=1,
            lexexch=" ".join(map(str, lexx_typat))
        )

from abipy.core.testing import AbipyTest

class LdauLexxTest(AbipyTest):

    def test_nio(self):
        """Test LdauParams and LexxParams."""
        structure = data.structure_from_ucell("NiO")
        pseudos = data.pseudos("28ni.paw", "8o.2.paw")

        u = 8.0
        luj_params = LdauParams(usepawu=1, structure=structure)
        luj_params.luj_for_symbol("Ni", l=2, u=u, j=0.1*u, unit="eV")
        vars = luj_params.to_abivars()

        self.assertTrue(vars["usepawu"] == 1),
        self.assertTrue(vars["lpawu"] ==  "2 -1"),
        self.assertTrue(vars["upawu"] == "8.0 0.0 eV"),
        self.assertTrue(vars["jpawu"] == "0.8 0.0 eV"),

        # Cannot add UJ for non-existent species.
        with self.assertRaises(ValueError):
            luj_params.luj_for_symbol("Foo", l=2, u=u, j=0.1*u, unit="eV")

        # Cannot overwrite UJ.
        with self.assertRaises(ValueError):
            luj_params.luj_for_symbol("Ni", l=1, u=u, j=0.1*u, unit="eV")

        lexx_params = LexxParams(structure)
        lexx_params.lexx_for_symbol("Ni", l=2)
        vars = lexx_params.to_abivars()

        self.assertTrue(vars["useexexch"] == 1),
        self.assertTrue(vars["lexexch"] ==  "2 -1"),

        # Cannot add LEXX for non-existent species.
        with self.assertRaises(ValueError):
            lexx_params.lexx_for_symbol("Foo", l=2)
                                                                            
        # Cannot overwrite LEXX.
        with self.assertRaises(ValueError):
            lexx_params.lexx_for_symbol("Ni", l=1)
