#  subunit: extensions to python unittest to get test results from subprocesses.
#  Copyright (C) 2009  Robert Collins <robertc@robertcollins.net>
#
#  Licensed under either the Apache License, Version 2.0 or the BSD 3-clause
#  license at the users choice. A copy of both licenses are available in the
#  project source as Apache-2.0 and BSD. You may not use this file except in
#  compliance with one of these two licences.
#  
#  Unless required by applicable law or agreed to in writing, software
#  distributed under these licenses is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
#  license you chose for the specific language governing permissions and
#  limitations under that license.
#


from optparse import OptionParser
import sys

from testtools import StreamResultRouter

from subunit import (
    DiscardStream, ProtocolTestCase, ByteStreamToStreamResult,
    StreamResultToBytes,
    )


def make_options(description):
    parser = OptionParser(description=description)
    parser.add_option(
        "--no-passthrough", action="store_true",
        help="Hide all non subunit input.", default=False,
        dest="no_passthrough")
    parser.add_option(
        "-o", "--output-to",
        help="Send the output to this path rather than stdout.")
    parser.add_option(
        "-f", "--forward", action="store_true", default=False,
        help="Forward subunit stream on stdout.")
    return parser


def run_tests_from_stream(input_stream, result, passthrough_stream=None,
                          forward_stream=None, protocol_version=1):
    """Run tests from a subunit input stream through 'result'.

    Non-test events - top level file attachments - are expected to be
    dropped by v2 StreamResults at the present time (as all the analysis code
    is in ExtendedTestResult API's), so to implement passthrough_stream they
    are diverted and copied directly when that is set.

    :param input_stream: A stream containing subunit input.
    :param result: A TestResult that will receive the test events.
        NB: This should be an ExtendedTestResult for v1 and a StreamResult for
        v2.
    :param passthrough_stream: All non-subunit input received will be
        sent to this stream.  If not provided, uses the ``TestProtocolServer``
        default, which is ``sys.stdout``.
    :param forward_stream: All subunit input received will be forwarded
        to this stream.  If not provided, uses the ``TestProtocolServer``
        default, which is to not forward any input.
    :param protocol_version: What version of the subunit protocol to expect.
    """
    orig_result = None
    if 1==protocol_version:
        test = ProtocolTestCase(
            input_stream, passthrough=passthrough_stream,
            forward=forward_stream)
    elif 2==protocol_version:
        if passthrough_stream is not None:
            # As the StreamToExtendedDecorator discards non-test events
            # we merely have to copy them IFF they are requested.
            passthrough_result = StreamResultToBytes(passthrough_stream)
            orig_result = result
            result = StreamResultRouter(result)
            result.map(passthrough_result, 'test_id', test_id=None)
            orig_result.startTestRun()
        test = ByteStreamToStreamResult(input_stream,
            non_subunit_name='stdout')
    else:
        raise Exception("Unknown protocol version.")
    result.startTestRun()
    test.run(result)
    if orig_result is not None:
        orig_result.stopTestRun()
    result.stopTestRun()


def filter_by_result(result_factory, output_path, passthrough, forward,
                     input_stream=sys.stdin, protocol_version=1):
    """Filter an input stream using a test result.

    :param result_factory: A callable that when passed an output stream
        returns a TestResult.  It is expected that this result will output
        to the given stream.
    :param output_path: A path send output to.  If None, output will be go
        to ``sys.stdout``.
    :param passthrough: If True, all non-subunit input will be sent to
        ``sys.stdout``.  If False, that input will be discarded.
    :param forward: If True, all subunit input will be forwarded directly to
        ``sys.stdout`` as well as to the ``TestResult``.
    :param input_stream: The source of subunit input.  Defaults to
        ``sys.stdin``.
    :param protocol_version: The subunit protocol version to expect.
    :return: A test result with the resultts of the run.
    """
    if passthrough:
        passthrough_stream = sys.stdout
    else:
        if 1==protocol_version:
            passthrough_stream = DiscardStream()
        else:
            passthrough_stream = None

    if forward:
        forward_stream = sys.stdout
    else:
        forward_stream = DiscardStream()

    if output_path is None:
        output_to = sys.stdout
    else:
        output_to = file(output_path, 'wb')

    try:
        result = result_factory(output_to)
        run_tests_from_stream(
            input_stream, result, passthrough_stream, forward_stream,
            protocol_version=protocol_version)
    finally:
        if output_path:
            output_to.close()
    return result


def run_filter_script(result_factory, description, post_run_hook=None):
    """Main function for simple subunit filter scripts.

    Many subunit filter scripts take a stream of subunit input and use a
    TestResult to handle the events generated by that stream.  This function
    wraps a lot of the boiler-plate around that by making a script with
    options for handling passthrough information and stream forwarding, and
    that will exit with a successful return code (i.e. 0) if the input stream
    represents a successful test run.

    :param result_factory: A callable that takes an output stream and returns
        a test result that outputs to that stream.
    :param description: A description of the filter script.
    """
    parser = make_options(description)
    (options, args) = parser.parse_args()
    result = filter_by_result(
        result_factory, options.output_to, not options.no_passthrough,
        options.forward)
    if post_run_hook:
        post_run_hook(result)
    if result.wasSuccessful():
        sys.exit(0)
    else:
        sys.exit(1)
