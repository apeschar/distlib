#
# Copyright (C) 2012 Vinay Sajip. All rights reserved.
#
import bisect
import io
import os
import sys
import zipimport

from .util import cached_property

class Resource(object):
    def __init__(self, finder, name):
        self.finder = finder
        self.name = name

    def stream(self):
        if self.is_container:
            raise ValueError("A container resource can't be returned as a "
                             "stream")
        return io.BytesIO(self.bytes)

    @cached_property
    def bytes(self):
        if self.is_container:
            raise ValueError("A container resource can't be returned as "
                             "bytes")
        return self.finder.get_bytes(self)

    @cached_property
    def resources(self):
        if not self.is_container:
            raise ValueError("A non-container resource can't be queried "
                             "for its contents")
        return self.finder.get_resources(self)

    @cached_property
    def is_container(self):
        return self.finder.is_container(self)

class ResourceFinder(object):
    """
    Resource finder for file system resources.
    """
    def __init__(self, module):
        self.module = module
        self.loader = getattr(module, '__loader__', None)
        f = os.path.dirname(getattr(module, '__file__', ''))
        parts = module.__name__.split('.')
        for p in parts:
            f = os.path.dirname(f)
        self.base = f

    def _make_path(self, resource_name):
        parts = self.module.__name__.split('.')
        parts.append(resource_name)
        result = os.sep.join(parts)
        if self.base:
            result = os.path.join(self.base, result)
        return result

    def _find(self, path):
        return os.path.exists(path)

    def get_resource(self, resource_name):
        path = self._make_path(resource_name)
        if not self._find(path):
            result = None
        else:
            result = Resource(self, resource_name)
            result.path = path
        return result

    def get_bytes(self, resource):
        with open(resource.path, 'rb') as f:
            return f.read()

    def get_resources(self, resource):
        def allowed(f):
            return f != '__pycache__' and not f.endswith(('.pyc', '.pyo'))
        return set([f for f in os.listdir(resource.path) if allowed(f)])

    def is_container(self, resource):
        return os.path.isdir(resource.path)

class ZipResourceFinder(ResourceFinder):
    """
    Resource finder for resources in .zip files.
    """
    def __init__(self, module):
        super(ZipResourceFinder, self).__init__(module)
        self.base = None
        self.index = sorted(self.loader._files)

    def _find(self, path):
        if path in self.loader._files:
            result = True
        else:
            path = '%s%s' % (path, os.sep)
            i = bisect.bisect(self.index, path)
            try:
                result = self.index[i].startswith(path)
            except IndexError:
                result = False
        return result
    
    def get_bytes(self, resource):
        return self.loader.get_data(resource.path)

    def get_resources(self, resource):
        path = '%s%s' % (resource.path, os.sep)
        plen = len(path)
        result = set()
        i = bisect.bisect(self.index, path)
        while i < len(self.index):
            if not self.index[i].startswith(path):
                break
            result.add(self.index[i][plen:])
            i += 1
        return result

    def is_container(self, resource):
        path = '%s%s' % (resource.path, os.sep)
        i = bisect.bisect(self.index, path)
        try:
            result = self.index[i].startswith(path)
        except IndexError:
            result = False
        return result

_finder_registry = {
    type(None): ResourceFinder,
    zipimport.zipimporter: ZipResourceFinder
}

def register_finder(loader, finder_maker):
    _finder_registry[type(loader)] = finder_maker

_finder_cache = {}

def finder(package):
    if package in _finder_cache:
        result = _finder_cache[package]
    else:
        if package not in sys.modules:
            __import__(package)
        module = sys.modules[package]
        loader = getattr(module, '__loader__', None)
        finder_maker = _finder_registry.get(type(loader))
        if finder_maker is None:
            raise ValueError('Unable to locate finder for %r' % package)
        result = finder_maker(module)
        _finder_cache[package] = result
    return result