# -*- coding: utf-8 -*-
"""
Meta tools for raw datasets
"""
from abc import ABCMeta
from contextlib import suppress

class MetaRawDataset(ABCMeta):
    """
    Metaclass for AbstractRawDataset. 
    
    This metaclass allows to determine the valid metadata that has been defined using the
    ExperimentalParameter class descriptor as class variables. For example, the AbstractRawDataset
    class already has some built-in ExperimentalParameter descriptors (date, notes, etc.)
    """
    
    def __init__(cls, clsname, bases, clsdict):
        super().__init__(clsname, bases, clsdict)

        if not hasattr(cls, 'valid_metadata'):
            cls.valid_metadata = set([])
        
        # valid metadata as defined on the local class
        # Only metadata defined via the ExperimentalParameter descriptor will appear in
        # instance.metadata
        local_valid_metadata = {name for name, parameter in cls.__dict__.items() 
                                if isinstance(parameter, ExperimentalParameter)}
        cls.valid_metadata = cls.valid_metadata.union(local_valid_metadata)

        # If available, also include valid metadata from superclasses
        with suppress(AttributeError):
            cls.valid_metadata = set.union(cls.valid_metadata, super().valid_metadata) 

class MetaHDF5Dataset(ABCMeta):
    """
    Metaclass for DiffractionDataset.

    This metaclass allows to determine the valid metadata that has been defined using the
    HDF5ExperimentalParameter class descriptor as class variables.
    """

    def __init__(cls, clsname, bases, clsdict):
        super().__init__(clsname, bases, clsdict)

        if not hasattr(cls, 'valid_metadata'):
            cls.valid_metadata = set([])

        # valid metadata as defined on the local class
        # Only metadata defined via the ExperimentalParameter descriptor will appear in
        # instance.metadata
        local_valid_metadata = {name for name, parameter in cls.__dict__.items() 
                                if isinstance(parameter, HDF5ExperimentalParameter)}
        cls.valid_metadata = cls.valid_metadata.union(local_valid_metadata)

        # If available, also include valid metadata from superclasses
        with suppress(AttributeError):
            cls.valid_metadata = set.union(cls.valid_metadata, super().valid_metadata) 

class ExperimentalParameter:
    """
    Descriptor to experimental parameters and metadata, with default values and
    forced types.

    Parameters
    ----------
    name : str
        Parameter name
    ptype : type or callable
        Parameter type, e.g. float, or callable, e.g. numpy.array. 
    default : object or None
        Default value of the parameter. If None, no default value is set. Hence, the
        default value can never be None.
    """
    __slots__ = ('name', 'type', 'default')

    def __init__(self, name, ptype, default = None):
        self.name = name
        self.type = ptype
        self.default = default
    
    def __get__(self, instance, cls):
        if instance is None:
            return self
        return instance.__dict__.get(self.name, self.default)
    
    def __set__(self, instance, value):
        """ If the value cannot be cast to the expected type, a TypeError is raised. """
        try:
            value = self.type(value)
        except ValueError:
            raise TypeError('Experimental parameter {} expects values of type \
                             {}, but received {}'.format(self.name, self.type, value))
        else:
             instance.__dict__[self.name] = value

class HDF5ExperimentalParameter(ExperimentalParameter):

    def __get__(self, instance, cls):
        value = instance.experimental_parameters_group.attrs.get(self.name, default = self.default)
        return self.type(value) if value is not None else None

    def __set__(self, instance, value):
        if (value is None) and (self.default is not None):
            value = self.default
        instance.experimental_parameters_group.attrs[self.name] = value
    
    def __delete__(self, instance):
        del instance.experimental_parameters_group.attrs[self.name]