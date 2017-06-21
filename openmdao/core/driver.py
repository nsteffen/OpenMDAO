"""Define a base class for all Drivers in OpenMDAO."""

from six import iteritems

import numpy as np

from openmdao.utils.options_dictionary import OptionsDictionary


class Driver(object):
    """
    Top-level container for the systems and drivers.

    Attributes
    ----------
    fail : bool
        Reports whether the driver ran successfully.
    options : <OptionsDictionary>
        Dictionary with general pyoptsparse options.
    _problem : <Problem>
        Pointer to the containing problem.
    supports : <OptionsDictionary>
        Provides a consistant way for drivers to declare what features they support.
    _designvars : dict
        Contains all design variable info.
    _cons : dict
        Contains all constraint info.
    _objs : dict
        Contains all objective info.
    _responses : dict
        Contains all response info.
    """

    def __init__(self):
        """
        Initialize the driver.
        """
        self._problem = None
        self._designvars = None
        self._cons = None
        self._objs = None
        self._responses = None
        self.options = OptionsDictionary()

        # What the driver supports.
        self.supports = OptionsDictionary()
        self.supports.declare('inequality_constraints', type_=bool, default=False)
        self.supports.declare('equality_constraints', type_=bool, default=False)
        self.supports.declare('linear_constraints', type_=bool, default=False)
        self.supports.declare('two_sided_constraints', type_=bool, default=False)
        self.supports.declare('multiple_objectives', type_=bool, default=False)
        self.supports.declare('integer_design_vars', type_=bool, default=False)
        self.supports.declare('gradients', type_=bool, default=False)
        self.supports.declare('active_set', type_=bool, default=False)

        # TODO, support these in Openmdao blue
        self.supports.declare('integer_design_vars', type_=bool, default=False)

        self.fail = False

    def _setup_driver(self, problem):
        """
        Prepare the driver for execution.

        This is the final thing to run during setup.

        Parameters
        ----------
        problem : <Problem>
            Pointer to the containing problem.
        """
        self._problem = problem
        model = problem.model

        # Gather up the information for design vars.
        self._designvars = model.get_design_vars(recurse=True)

        self._responses = model.get_responses(recurse=True)
        self._objs = model.get_objectives(recurse=True)
        self._cons = model.get_constraints(recurse=True)

    def get_design_var_values(self):
        """
        Return the design variable values.

        This is called to gather the initial design variable state.

        Returns
        -------
        dict
           Dictionary containing values of each design variable.
        """
        vec = self._problem.model._outputs._views_flat
        dv_dict = {}
        for name, meta in iteritems(self._designvars):
            scaler = meta['scaler']
            adder = meta['adder']
            indices = meta['indices']
            if indices is None:
                val = vec[name].copy()
            else:
                val = vec[name][indices]

            # Scale design variable values
            if adder is not None:
                val += adder
            if scaler is not None:
                val *= scaler

            dv_dict[name] = val

        return dv_dict

    def set_design_var(self, name, value):
        """
        Set the value of a design variable.

        Parameters
        ----------
        name : str
            Global pathname of the design variable.
        value : float or ndarray
            Value for the design variable.
        """
        meta = self._designvars[name]
        scaler = meta['scaler']
        adder = meta['adder']
        indices = meta['indices']
        if indices is None:
            indices = slice(None)

        desvar = self._problem.model._outputs._views_flat[name]
        desvar[indices] = value

        # Scale design variable values
        if scaler is not None:
            desvar[indices] *= 1.0 / scaler
        if adder is not None:
            desvar[indices] -= adder

    def get_response_values(self):
        """
        Return response values.

        Returns
        -------
        dict
           Dictionary containing values of each response.
        """
        # TODO: finish this method when we have a driver that requires it.
        pass

    def get_objective_values(self):
        """
        Return objective values.

        Returns
        -------
        dict
           Dictionary containing values of each objective.
        """
        vec = self._problem.model._outputs._views_flat
        obj_dict = {}
        for name, meta in iteritems(self._objs):
            scaler = meta['scaler']
            adder = meta['adder']
            indices = meta['indices']
            if indices is None:
                val = vec[name].copy()
            else:
                val = vec[name][indices]

            # Scale objectives
            if adder is not None:
                val += adder
            if scaler is not None:
                val *= scaler

            obj_dict[name] = val

        return obj_dict

    def get_constraint_values(self, ctype='all', lintype='all'):
        """
        Return constraint values.

        Parameters
        ----------
        ctype : string
            Default is 'all'. Optionally return just the inequality constraints
            with 'ineq' or the equality constraints with 'eq'.

        lintype : string
            Default is 'all'. Optionally return just the linear constraints
            with 'linear' or the nonlinear constraints with 'nonlinear'.

        Returns
        -------
        dict
           Dictionary containing values of each constraint.
        """
        vec = self._problem.model._outputs._views_flat
        con_dict = {}

        for name, meta in iteritems(self._cons):

            if lintype == 'linear' and meta['linear'] is False:
                continue

            if lintype == 'nonlinear' and meta['linear']:
                continue

            if ctype == 'eq' and meta['equals'] is None:
                continue

            if ctype == 'ineq' and meta['equals'] is not None:
                continue

            scaler = meta['scaler']
            adder = meta['adder']
            indices = meta['indices']

            if indices is None:
                val = vec[name].copy()
            else:
                val = vec[name][indices]

            # Scale objectives
            if adder is not None:
                val += adder
            if scaler is not None:
                val *= scaler

            # TODO: Need to get the allgathered values? Like:
            # cons[name] = self._get_distrib_var(name, meta, 'constraint')
            con_dict[name] = val

        return con_dict

    def run(self):
        """
        Execute this driver.

        The base `Driver` just runs the model. All other drivers overload
        this method.

        Returns
        -------
        boolean
            Failure flag; True if failed to converge, False is successful.
        """
        return self._problem.model._solve_nonlinear()

    def _compute_total_derivs(self, of=None, wrt=None, return_format='flat_dict',
                              global_names=True):
        """
        Compute derivatives of desired quantities with respect to desired inputs.

        All derivatives are returned using driver scaling.

        Parameters
        ----------
        of : list of variable name strings or None
            Variables whose derivatives will be computed. Default is None, which
            uses the driver's objectives and constraints.
        wrt : list of variable name strings or None
            Variables with respect to which the derivatives will be computed.
            Default is None, which uses the driver's desvars.
        return_format : string
            Format to return the derivatives. Default is a 'flat_dict', which
            returns them in a dictionary whose keys are tuples of form (of, wrt). For
            the scipy optimizer, 'array' is also supported.
        global_names : bool
            Set to True when passing in global names to skip some translation steps.

        Returns
        -------
        derivs : object
            Derivatives in form requested by 'return_format'.
        """
        prob = self._problem

        if return_format == 'dict':

            derivs = prob._compute_total_derivs(of=of, wrt=wrt, return_format=return_format,
                                                global_names=global_names)

            for okey, oval in iteritems(derivs):
                for ikey, val in iteritems(oval):

                    imeta = self._designvars[ikey]
                    ometa = self._responses[okey]

                    iscaler = imeta['scaler']
                    oscaler = ometa['scaler']

                    # Scale response side
                    if oscaler is not None:
                        val *= oscaler

                    # Scale design var side
                    if iscaler is not None:
                        val *= 1.0 / iscaler

        elif return_format == 'array':

            # Compute the derivatives in dict format, and then convert to array.
            derivs = prob._compute_total_derivs(of=of, wrt=wrt, return_format='dict',
                                                global_names=global_names)

            # Use sizes pre-computed in derivs for ease
            osize = 0
            isize = 0
            do_wrt = True
            Jslices = {}
            for okey, oval in iteritems(derivs):
                if do_wrt:
                    for ikey, val in iteritems(oval):
                        istart = isize
                        isize += val.shape[1]
                        Jslices[ikey] = slice(istart, isize)

                do_wrt = False
                ostart = osize
                osize += oval[ikey].shape[0]
                Jslices[okey] = slice(ostart, osize)

            new_derivs = np.zeros((osize, isize))

            # Apply driver ref/ref0 and position subjac into array jacobian.
            for okey, oval in iteritems(derivs):
                for ikey, val in iteritems(oval):

                    imeta = self._designvars[ikey]
                    ometa = self._responses[okey]

                    iscaler = imeta['scaler']
                    oscaler = ometa['scaler']

                    # Scale response side
                    if oscaler is not None:
                        val *= oscaler

                    # Scale design var side
                    if iscaler is not None:
                        val *= 1.0 / iscaler

                    new_derivs[Jslices[okey], Jslices[ikey]] = val

            derivs = new_derivs

        else:
            msg = "Derivative scaling by the driver only supports the 'dict' format at present."
            raise RuntimeError(msg)

        return derivs

    def get_req_procs(self, model):
        """
        Return min and max MPI processes usable by this Driver for the model.

        This should be overridden by Drivers that can use more processes than
        the model uses, e.g., DOEDriver.

        Parameters
        ----------
        model : <System>
            Top level <System> that contains the entire model.

        Returns
        -------
        tuple : (int, int or None)
            A tuple of the form (min_procs, max_procs), indicating the min
            and max processors usable by this `Driver` and the given model.
            max_procs can be None, indicating all available procs can be used.
        """
        return model.get_req_procs()
