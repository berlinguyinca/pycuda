Frequently Asked Questions
==========================

How about multiple GPUs?
------------------------

Two ways:

* Allocate two contexts, juggle (:meth:`pycuda.driver.Context.push` and
  :meth:`pycuda.driver.Context.pop`) them from that one process.
* Work with several threads. As of Version 0.90.2, PyCuda will actually 
  release the `GIL <http://en.wikipedia.org/wiki/Global_Interpreter_Lock>`_
  while it is waiting for CUDA operations to finish.

My program terminates after a launch failure. Why?
--------------------------------------------------

You're probably seeing something like this::

  Traceback (most recent call last):
    File "fail.py", line 32, in <module>
      cuda.memcpy_dtoh(a_doubled, a_gpu)
  RuntimeError: cuMemcpyDtoH failed: launch failed
  terminate called after throwing an instance of 'std::runtime_error'
    what():  cuMemFree failed: launch failed
  zsh: abort      python fail.py

What's going on here? First of all, recall that launch failures in 
CUDA are asynchronous. So the actual traceback does not point to
the failed kernel launch, it points to the next CUDA request after
the failed kernel.

Next, as far as I can tell, a CUDA context becomes invalid after a launch
failure, and all following CUDA calls in that context fail. Now, that includes
cleanup (see the :cfunc:`cuMemFree` in the traceback?) that PyCuda tries to perform
automatically. Here, a bit of PyCuda's C++ heritage shows through. While 
performing cleanup, we are processing an exception (the launch failure
reported by :cfunc:`cuMemcpyDtoH`). If another exception occurs during 
exception processing, C++ gives up and aborts the program with a message.

In principle, this could be handled better. If you're willing to dedicate time
to this, I'll likely take your patch.

Are the CUBLAS APIs available via PyCuda?  
-----------------------------------------

No. I would be more than happy to make them available, but that would be mostly
either-or with the rest of PyCuda, because of the following sentence in the
CUDA programming guide:

   [CUDA] is composed of two APIs:

   * A low-level API called the CUDA driver API,
   * A higher-level API called the CUDA runtime API that is implemented on top of
     the CUDA driver API.

   These APIs are mutually exclusive: An application should use either one or the
   other.

PyCuda is based on the driver API. CUBLAS uses the high-level API. Once *can*
violate this rule without crashing immediately. But sketchy stuff does happen.
Instead, for BLAS-1 operations, PyCuda comes with a class called GPUArray that
essentially reimplements that part of CUBLAS.

If you dig into the history of PyCuda, you'll find that, at one point, I
did have rudimentary CUBLAS wrappers. I removed them because of the above
issue. If you would like to make CUBLAS wrappers, feel free to use these
rudiments as a starting point. That said, Arno Pähler's python-cuda has
complete :mod:`ctypes`-based wrappers for CUBLAS. I don't think they interact natively
with numpy, though.

Acknowledgements
================

* Gert Wohlgemuth ported PyCuda to MacOS X and contributed large parts of
  :class:`pycuda.gpuarray.GPUArray`.
* Znah on the Nvidia forums contributed fixes for Windows XP.
* Cosmin Stejerean provided multiple patches for PyCuda's build system.

Licensing
=========

PyCuda is licensed to you under the MIT/X Consortium license:

Copyright (c) 2008 Andreas Klöckner

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.
