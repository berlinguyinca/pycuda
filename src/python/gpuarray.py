from __future__ import division
import numpy
import pycuda._kernel as kernel
import random as random
from pytools import memoize
import pycuda.driver as drv


def splay(n, min_threads=None, max_threads=128, max_blocks=80):
    # stolen from cublas

    if min_threads is None:
        min_threads = WARP_SIZE

    if n < min_threads:
        block_count = 1
        elems_per_block = n
        threads_per_block = min_threads
    elif n < (max_blocks * min_threads):
        block_count = (n + min_threads - 1) // min_threads
        threads_per_block = min_threads
        elems_per_block = threads_per_block
    elif n < (max_blocks * max_threads):
        block_count = max_blocks
        grp = (n + min_threads - 1) // min_threads
        threads_per_block = ((grp + max_blocks -1) // max_blocks) * min_threads
        elems_per_block = threads_per_block
    else:
        block_count = max_blocks
        threads_per_block = max_threads
        grp = (n + min_threads - 1) // min_threads
        grp = (grp + max_blocks - 1) // max_blocks
        elems_per_block = grp * min_threads

    #print "bc:%d tpb:%d epb:%d" % (block_count, threads_per_block, elems_per_block)
    return block_count, threads_per_block, elems_per_block








WARP_SIZE = 32



class GPUArray(object): 
    """A GPUArray is used to do array based calculation on the GPU. 

    This is mostly supposed to be a numpy-workalike. Operators
    work on an element-by-element basis, just like numpy.ndarray.
    """

    def __init__(self, shape, dtype=numpy.float32, stream=None, allocator=drv.mem_alloc,cuda_device=0):
        try:
            drv.init()
            ctx = drv.Device(0).make_context()
        except RuntimeError:
            "device is already initialized! so we ignore this ugly, but works for now"
        
        #which device are we working on
        self.cuda_device = cuda_device
        
        #internal shape
        self.shape = shape
        
        #internal type
        self.dtype = numpy.dtype(dtype)

        from pytools import product
        
        #internal size
        self.size = product(shape)

        self.allocator = allocator
        if self.size:
            self.gpudata = self.allocator(self.size * self.dtype.itemsize)
        else:
            self.gpudata = None
        self.stream = stream

        self._update_kernel_kwargs()

    def _update_kernel_kwargs(self):
        block_count, threads_per_block, elems_per_block = splay(self.size, WARP_SIZE, 128, 80)

        self._kernel_kwargs = {
                "block": (threads_per_block,1,1), 
                "grid": (block_count,1),
                "stream": self.stream,
        }

    @classmethod
    def compile_kernels(cls):
        # useful for benchmarking
        kernel._compile_kernels(cls)
    

    def set(self, ary, stream=None):
        assert ary.size == self.size
        assert ary.dtype == self.dtype
        if self.size:
            drv.memcpy_htod(self.gpudata, ary, stream)

    def get(self, ary=None, stream=None, pagelocked=False):
        if ary is None:
            if pagelocked:
                ary = drv.pagelocked_empty(self.shape, self.dtype)
            else:
                ary = numpy.empty(self.shape, self.dtype)
        else:
            assert ary.size == self.size
            assert ary.dtype == self.dtype
        if self.size:
            drv.memcpy_dtoh(ary, self.gpudata)
        return ary

    def __str__(self):
        return str(self.get())

    def __repr__(self):
        return repr(self.get())




    # kernel invocation wrappers ----------------------------------------------
    def _axpbyz(self, selffac, other, otherfac, out):
        """Compute ``out = selffac * self + otherfac*other``, 
        where `other` is a vector.."""
        assert self.dtype == numpy.float32
        assert self.shape == other.shape
        assert self.dtype == other.dtype

        if self.stream is not None or other.stream is not None:
            assert self.stream is other.stream

        kernel._get_axpbyz_kernel()(numpy.float32(selffac), self.gpudata, 
                numpy.float32(otherfac), other.gpudata, 
                out.gpudata, numpy.int32(self.size),
                **self._kernel_kwargs)

        return out

    def _axpbz(self, selffac, other, out):
        """Compute ``out = selffac * self + other``, where `other` is a scalar."""
        assert self.dtype == numpy.float32

        kernel._get_axpbz_kernel()(
                numpy.float32(selffac), self.gpudata,
                numpy.float32(other),
                out.gpudata, numpy.int32(self.size),
                **self._kernel_kwargs)

        return out

    def _elwise_multiply(self, other, out):
        assert self.dtype == numpy.float32
        assert self.dtype == numpy.float32

        kernel._get_multiply_kernel()(
                self.gpudata, other.gpudata,
                out.gpudata, numpy.int32(self.size),
                **self._kernel_kwargs)

        return out

    def _rdiv_scalar(self, other, out):
        """Divides an array by a scalar::
          
           y = n / self 
        """

        assert self.dtype == numpy.float32

        kernel._get_rdivide_scalar_kernel()(
                self.gpudata,
                numpy.float32(other),
                out.gpudata, numpy.int32(self.size),
                **self._kernel_kwargs)

        return out

    def _div(self, other, out):
        """Divides an array by another array."""

        assert self.dtype == numpy.float32
        assert self.shape == other.shape
        assert self.dtype == other.dtype

        block_count, threads_per_block, elems_per_block = splay(self.size, WARP_SIZE, 128, 80)

        kernel._get_divide_kernel()(self.gpudata, other.gpudata,
                out.gpudata, numpy.int32(self.size),
                **self._kernel_kwargs)

        return out



    # operators ---------------------------------------------------------------
    def __add__(self, other):
        """Add an array with an array or an array with a scalar."""

        if isinstance(other, (int, float, complex)):
            # add a scalar
            if other == 0:
                return self
            else:
                result = GPUArray(self.shape, self.dtype)
                return self._axpbz(1, other, result)
        else:
            # add another vector
            result = GPUArray(self.shape, self.dtype)
            return self._axpbyz(1, other, 1, result)

    __radd__ = __add__

    def __sub__(self, other):
        """Substract an array from an array or a scalar from an array."""

        if isinstance(other, (int, float, complex)):
            # if array - 0 than just return the array since its the same anyway

            if other == 0:
                return self
            else:
                # create a new array for the result
                result = GPUArray(self.shape, self.dtype)
                return self._axpbz(1, -other, result)
        else:
            result = GPUArray(self.shape, self.dtype)
            return self._axpbyz(1, other, -1, result)

    def __rsub__(self,other):
        """Substracts an array by a scalar or an array:: 

           x = n - self
        """
        assert isinstance(other, (int, float, complex))

        # if array - 0 than just return the array since its the same anyway
        if other == 0:
            return self
        else:
            # create a new array for the result
            result = GPUArray(self.shape, self.dtype)
            return self._axpbz(-1, other, result)

    def __iadd__(self, other):
        return self._axpbyz(1, other, 1, self)

    def __isub__(self, other):
        return self._axpbyz(1, other, -1, self)

    def __neg__(self):
        result = GPUArray(self.shape, self.dtype)
        return self._axpbz(-1, 0, result)

    def __mul__(self, other):
        result = GPUArray(self.shape, self.dtype)
        if isinstance(other, (int, float, complex)):
            return self._axpbz(other, 0, result)
        else:
            return self._elwise_multiply(other, result)

    def __rmul__(self, scalar):
        result = GPUArray(self.shape, self.dtype)
        return self._axpbz(scalar, 0, result)

    def __imul__(self, scalar):
        return self._axpbz(scalar, 0, self)

    def __div__(self, other):
        """Divides an array by an array or a scalar::

           x = self / n
        """
        if isinstance(other, (int, float, complex)):
            # if array - 0 than just return the array since its the same anyway
            if other == 0:
                return self
            else:
                # create a new array for the result
                result = GPUArray(self.shape, self.dtype)
                return self._axpbz(1/other, 0, result)
        else:
            result = GPUArray(self.shape, self.dtype)
            return self._div(other, result)

    def __rdiv__(self,other):
        """Divides an array by a scalar or an array::

           x = n / self
        """

        if isinstance(other, (int, float, complex)):
            # if array - 0 than just return the array since its the same anyway
            if other == 0:
                return self
            else:
                # create a new array for the result
                result = GPUArray(self.shape, self.dtype)
                return self._rdiv_scalar(other, result)
        else:
            result = GPUArray(self.shape, self.dtype)

            assert self.dtype == numpy.float32
            assert self.shape == other.shape
            assert self.dtype == other.dtype

            kernel._get_divide_kernel()(other.gpudata, self.gpudata,
                    out.gpudata, numpy.int32(self.size),
                    **self._kernel_kwargs)

            return result


    def fill(self, value):
        """fills the array with the specified value"""
        assert self.dtype == numpy.float32

        kernel._get_fill_kernel()(numpy.float32(value), self.gpudata, numpy.int32(self.size),**self._kernel_kwargs
)

        return self

    def randn(self):
        """fills the array with random data
    
            calculates random numbers for each element of the array
            
        """

        kernel._get_random_kernel()(self.gpudata,numpy.float32(random.random()), numpy.int32(self.size),
                **self._kernel_kwargs)
            
        return self
        
    def bind_to_texref(self, texref):
        texref.set_address(self.gpudata, self.size*self.dtype.itemsize)


    def __len__(self):
        """returns the len of the internal array"""
        return self.size


    def __abs__(self):
        """calculates the abs value of all values in the array"""

        assert self.dtype == numpy.float32

        result = GPUArray(self.shape, self.dtype)
        block_count, threads_per_block, elems_per_block = splay(self.size, WARP_SIZE, 128, 80)

        kernel._get_abs_kernel()(self.gpudata,result.gpudata,numpy.int32(self.size),
                block=(threads_per_block,1,1), grid=(block_count,1),
                stream=self.stream)

        return result

    def __pow__(self,other):
        """pow function::
 
           example:
                   array = pow(array)
                   array = pow(array,4)
                   array = pow(array,array)

        """
        result = GPUArray(self.shape, self.dtype)
        block_count, threads_per_block, elems_per_block = splay(self.size, WARP_SIZE, 128, 80)

        if isinstance(other, (int, float, complex)):

            kernel._get_pow_kernel()(numpy.float32(other),self.gpudata,result.gpudata,numpy.int32(self.size),
            block=(threads_per_block,1,1), grid=(block_count,1),
            stream=self.stream)

            return result
        else:
            assert self.shape == other.shape
            assert self.dtype == other.dtype

            kernel._get_pow_array_kernel()(self.gpudata,other.gpudata,result.gpudata,numpy.int32(self.size),
            block=(threads_per_block,1,1), grid=(block_count,1),
            stream=self.stream)
            
            return result

    def is_matrix(self):
        """returns if this is a matrix"""
        if(len(self.shape) == 1):
            return False
        return True


    def dot(self,matrix):
        """calculates the dot product of two matrixes::
        
           both matrixes need to be on the same gpu and need to have the same
           shapes
        """
        
        assert self.shape == matrix.shape
        assert self.dtype == matrix.dtype
        assert self.is_matrix() == True
        assert matrix.is_matrix() == True      

        result = GPUArray(self.shape, self.dtype)

        print "shape"
        print self.shape
        print "content"
        print self
        print "matrix content"
        print matrix
        
        kernel._get_dot_kernel()(self.gpudata,matrix.gpudata,result.gpudata,numpy.int32(self.size),**self._kernel_kwargs)

        print "result"
        return result
        
    def reverse(self):
        """Reverse the array::

           the first entry becomes the last entry. This is only valid for no matrix based arrays!

        """

        assert self.dtype == numpy.float32
        
        result = GPUArray(self.shape, self.dtype)

        kernel._get_reverse_kernel()(self.gpudata,result.gpudata,numpy.int32(self.size),**self._kernel_kwargs)

        return result


    def __invert__(self):
        """does the same as reverse"""
        return self.reverse()


    def fill_arange(self):
        """fills the array in an arranged way, like numpy"""

        block_count, threads_per_block, elems_per_block = splay(self.size, WARP_SIZE, 128, 80)
        kernel._get_arrange_kernel()(self.gpudata, numpy.int32(self.size),
                block=(threads_per_block,1,1), grid=(block_count,1),
                stream=self.stream)

        return self


    def __iter__(self):
        """iteration works over the internal array"""
        return GPUIterator(self.get())

    def __getitem__(self,key):
        """allows us to get objects using an index::

           this operation is extremly slow since we need to copy the array from the gpu
           to the cpu for each access
        """

        if self.is_matrix():
            #if its a matrix we return a gpu array so that we can calculate on it
            entry = self.get()[key]
            return to_gpu(entry)
        else:
            return self.get()[key]


class GPUIterator:
    """small helper to support iterations"""

    def __init__(self,target):
        self.target = target
        self.size = target.size
        self.count = 0

    def __iter__(self):
        return self

    def next(self):
        count = self.count + 1
        if count > self.target.size:
            raise StopIteration

        self.count = count

        return count

 
def arange(limit,dtype=numpy.float32):
    """arranges an array like the array function from numpy"""
    result = GPUArray((limit,), dtype)
  
    result.fill_arange() 
    return result


def to_gpu(ary, stream=None):
    """converts a numpy array to a GPUArray"""
    result = GPUArray(ary.shape, ary.dtype)
    result.set(ary, stream)
    return result


empty = GPUArray

def zeros(shape, dtype, stream=None):
    """creates an array of the given size and fills it with 0's"""
    result = GPUArray(shape, dtype, stream)
    result.fill(0)
    return result

def array(size,value=0):
    """creates a array of the given size"""
    return fill((size,),value)

def fill(shape,value, dtype=numpy.float32, stream=None):
    """creates an array of the given shape and fills it with the data"""
    result = GPUArray(shape, dtype, stream)
    result.fill(value)
    return result

def matrix(width,height,value=0):
    """creates a matrix of the given size"""
    return fill((width,height),value)
