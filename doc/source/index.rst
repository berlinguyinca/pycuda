Welcome to PyCuda's documentation!
==================================

PyCuda gives you easy, Pythonic access to `Nvidia <http://nvidia.com>`_'s `CUDA
<http://nvidia.com/cuda/>`_ parallel computation API. Several wrappers of the
CUDA API already exist--so why the need for PyCuda?

* Object cleanup tied to lifetime of objects. This idiom,
  often called 
  `RAII <http://en.wikipedia.org/wiki/Resource_Acquisition_Is_Initialization>`_
  in C++, makes it much easier to write correct, leak- and
  crash-free code. PyCuda knows about dependencies, too, so (for example)
  it won't detach from a context before all memory allocated in it is also
  freed.

* Convenience. Abstractions like :class:`pycuda.driver.SourceModule` and
  :class:`pycuda.gpuarray.GPUArray` make CUDA programming even more convenient
  than with Nvidia's C-based runtime.

* Completeness. PyCuda puts the full power of CUDA's driver API at your
  disposal, if you wish. 

* Automatic Error Checking. All CUDA errors are automatically translated
  into Python exceptions.

* Speed. PyCuda's base layer is written in C++, so all the niceties above
  are virtually free.

* Helpful Documentation. You're looking at it. ;)

Here's an example, to given you an impression::

  import pycuda.driver as drv
  import numpy

  drv.init()
  dev = drv.Device(0)
  ctx = dev.make_context()

  mod = drv.SourceModule("""
  __global__ void multiply_them(float *dest, float *a, float *b)
  {
    const int i = threadIdx.x;
    dest[i] = a[i] * b[i];
  }
  """)

  multiply_them = mod.get_function("multiply_them")

  a = numpy.random.randn(400).astype(numpy.float32)
  b = numpy.random.randn(400).astype(numpy.float32)

  dest = numpy.zeros_like(a)
  multiply_them(
          drv.Out(dest), drv.In(a), drv.In(b),
          block=(400,1,1))

  print dest-a*b

On the surface, this program will print a screenful of zeros. Behind
the scenes, a lot more interesting stuff is going on:

* PyCuda has compiled the CUDA source code and uploaded it to the card. 
  
  .. note:: This code doesn't have to be a constant--you can easily have Python
    generate the code you want to compile.

* PyCuda's numpy interaction code has automatically allocated
  space on the device, copied the numpy arrays *a* and *b* over,
  launched a 400x1x1 single-block grid, and copied *dest* back.

  Note that you can just as well keep your data on the card between
  kernel invocations--no need to copy data all the time.

Curious? Let's get started.

Contents
=========

.. toctree::
    :maxdepth: 2

    install
    tutorial
    driver
    array
    faq

Note that this guide will not explain CUDA programming and technology.  Please
refer to Nvidia's `programming documentation
<http://www.nvidia.com/object/cuda_learn.html>`_ for that.

PyCuda also has its own `web site <http://mathema.tician.de/software/pycuda>`_,
where you can find updates, new versions, documentation, and support.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

