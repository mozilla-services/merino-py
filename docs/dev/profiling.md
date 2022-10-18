# Profiling

As Merino runs as a single-threaded application using the asyncio-based
framework, it would be useful for engineers to get a good understanding
about how Merino performs and where it spends time and memory doing what
tasks to serve the requests. Local profiling offers us a way to look into
those low-level details.

We use [Scalene][1] as the profiler to conduct the profiling for Merino.
It's very easy to use, offers extremely detailed (at the line level)
insights with much lower overhead compared to other profilers.

## Usage

To start the profiling, you can run the following to start Merino with
Scalene:

```sh
$ make profile

# or you can run it directly

$ python -m scalene merino/main.py
```

Then you can send requests to Merino manually or through using other
load testing tools. Once that's done, you can terminate the Merino
application. It will automatically collect profiling outputs (CPU & Memory)
and open it in your browser.

## Understand the outputs

Out of the box, Scalene provides a very intuitive web interface to display
the profiling outputs. It's organized at the file (module) level. For each
file, it shows the CPU time and average memory usage for both the line profile
and the function profile of that module. You can also click on specific columns
to sort the lines or functions accordingly.

For more details of how to read the outputs, you can reference Scalene's
[documents][2].

Equipped with those insights, you can have a good understanding about the
application, identify hotspots, bottlenecks, or other findings that are
not easy to uncover by only reading the source code. And then, you can tweak
or fix those issues, test or profile it again to verify if the fix is working.

[1]: https://github.com/plasma-umass/scalene
[2]: https://github.com/plasma-umass/scalene#output
