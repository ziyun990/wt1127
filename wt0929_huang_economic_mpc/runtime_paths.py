"""Portable interpreter selection for the native simulator and COPT worker."""
import os,sys

def solver_python():
    return os.environ.get('WT_SOLVER_PYTHON',sys.executable)

def native_python():
    return os.environ.get('WT_NATIVE_PYTHON',sys.executable)
