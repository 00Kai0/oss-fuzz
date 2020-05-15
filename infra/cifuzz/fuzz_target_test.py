# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Test the functionality of the fuzz_target module."""

import os
import sys
import tempfile
import unittest
import unittest.mock

import parameterized
from pyfakefs import fake_filesystem_unittest

# Pylint has issue importing utils which is why error suppression is required.
# pylint: disable=wrong-import-position
# pylint: disable=import-error
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fuzz_target

# NOTE: This integration test relies on
# https://github.com/google/oss-fuzz/tree/master/projects/example project.
EXAMPLE_PROJECT = 'example'

# An example fuzzer that triggers an error.
EXAMPLE_FUZZER = 'example_crash_fuzzer'

# Location of files used for testing.
TEST_FILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'test_files')

# The return value of a successful call to utils.execute.
EXECUTE_SUCCESS_RETVAL = ('', '', 0)

# The return value of a failed call to utils.execute.
EXECUTE_FAILURE_RETVAL = ('', '', 1)


# TODO(metzman): Use patch from clusterfuzz/src/python/tests/test_libs/
# so that we don't need to accept this as an argument in every test method.
@unittest.mock.patch('utils.get_container_name', return_value='container')
class IsReproducibleUnitTest(fake_filesystem_unittest.TestCase):
  """Test is_reproducible function in the fuzz_target module."""

  def setUp(self):
    """Sets up dummy fuzz target to test is_reproducible method."""
    self.fuzz_target_bin = '/example/path'
    self.test_target = fuzz_target.FuzzTarget(self.fuzz_target_bin,
                                              fuzz_target.REPRODUCE_ATTEMPTS,
                                              '/example/outdir')

  def test_reproducible(self, _):
    """Tests that is_reproducible will return True, True if crash is
    detected."""
    self._set_up_fakefs()
    all_repro = [EXECUTE_FAILURE_RETVAL] * fuzz_target.REPRODUCE_ATTEMPTS
    with unittest.mock.patch('utils.execute', side_effect=all_repro) as patch:
      result = self.test_target.is_reproducible(TEST_FILES_PATH,
                                                self.fuzz_target_bin)
      self.assertEqual(result, (True, True))
      self.assertEqual(1, patch.call_count)

  def _set_up_fakefs(self):
    """Helper to setup pyfakefs and add important files to the fake
    filesystem."""
    self.setUpPyfakefs()
    self.fs.create_file(self.fuzz_target_bin)
    self.fs.add_real_directory(TEST_FILES_PATH)

  def test_flaky(self, _):
    """Tests that is_reproducible will return True, True if crash is
    detected on the last attempt."""
    self._set_up_fakefs()
    last_time_repro = [EXECUTE_SUCCESS_RETVAL] * 9 + [EXECUTE_FAILURE_RETVAL]
    with unittest.mock.patch('utils.execute',
                             side_effect=last_time_repro) as patch:
      self.assertTrue(
          self.test_target.is_reproducible(TEST_FILES_PATH,
                                           self.fuzz_target_bin))
      self.assertEqual(fuzz_target.REPRODUCE_ATTEMPTS, patch.call_count)

  def test_non_existent_fuzzer(self, _):
    """Tests that is_reproducible will report that it could not attempt
    reproduction if the fuzzer does not exist."""
    result = self.test_target.is_reproducible(TEST_FILES_PATH,
                                              '/non-existent-path')
    expected_result = (False, False)
    self.assertEqual(result, expected_result)

  def test_unreproducible(self, _):
    """Tests that is_reproducible returns (True, True) for a crash that cannot
    be reproduced."""
    all_unrepro = [EXECUTE_SUCCESS_RETVAL] * fuzz_target.REPRODUCE_ATTEMPTS
    self._set_up_fakefs()
    with unittest.mock.patch('utils.execute', side_effect=all_unrepro):
      result = self.test_target.is_reproducible(TEST_FILES_PATH,
                                                self.fuzz_target_bin)
      expected_result = (False, True)
      self.assertEqual(result, expected_result)

  def test_non_existent_testcase(self, _):
    """Tests that method reports it did not attempt reproduction if testcase
    doesn't exist."""
    self._set_up_fakefs()
    result = self.test_target.is_reproducible('/non-existent-path',
                                              self.fuzz_target_bin)
    expected_result = (False, False)
    self.assertEqual(result, expected_result)


class GetTestCaseUnitTest(unittest.TestCase):
  """Test get_test_case function in the fuzz_target module."""

  def setUp(self):
    """Sets up dummy fuzz target to test get_test_case method."""
    self.test_target = fuzz_target.FuzzTarget('/example/path', 10,
                                              '/example/outdir')

  def test_valid_error_string(self):
    """Tests that get_test_case returns the correct test case give an error."""
    test_case_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'test_files',
                                  'example_crash_fuzzer_output.txt')
    with open(test_case_path, 'r') as test_fuzz_output:
      parsed_test_case = self.test_target.get_test_case(test_fuzz_output.read())
    self.assertEqual(
        parsed_test_case,
        '/example/outdir/crash-ad6700613693ef977ff3a8c8f4dae239c3dde6f5')

  def test_invalid_error_string(self):
    """Tests that get_test_case will return None with a bad error string."""
    self.assertIsNone(self.test_target.get_test_case(''))
    self.assertIsNone(self.test_target.get_test_case(' Example crash string.'))


class DownloadLatestCorpusUnitTest(unittest.TestCase):
  """Test parse_fuzzer_output function in the cifuzz module."""

  def test_download_valid_projects_corpus(self):
    """Tests that a vaild fuzz target will return a corpus directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      test_target = fuzz_target.FuzzTarget('testfuzzer', 3, 'test_out')
      test_target.project_name = EXAMPLE_PROJECT
      test_target.target_name = EXAMPLE_FUZZER
      test_target.out_dir = tmp_dir
      with unittest.mock.patch('fuzz_target.download_and_unpack_zip',
                               return_value=tmp_dir) as mock:
        test_target.download_latest_corpus()
        (url, out_dir), _ = mock.call_args
        self.assertEqual(
            url,
            'https://storage.googleapis.com/example-backup.'
            'clusterfuzz-external.appspot.com/corpus/libFuzzer/'
            'example_crash_fuzzer/public.zip'
        )
        self.assertEqual(out_dir,
                         os.path.join(tmp_dir, 'backup_corpus', EXAMPLE_FUZZER))

  def test_download_invalid_projects_corpus(self):
    """Tests that a invaild fuzz target will not return None."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      test_target = fuzz_target.FuzzTarget('testfuzzer', 3, tmp_dir)
      corpus_path = test_target.download_latest_corpus()
      self.assertIsNone(corpus_path)
      test_target = fuzz_target.FuzzTarget('not_a_fuzzer', 3, tmp_dir,
                                           'not_a_project')
      corpus_path = test_target.download_latest_corpus()
      self.assertIsNone(corpus_path)


class IsCrashReportableUnitTest(fake_filesystem_unittest.TestCase):
  """Test is_crash_reportable method of fuzz_target.FuzzTarget."""

  def setUp(self):
    """Sets up dummy fuzz target to test is_crash_reportable method."""
    self.fuzz_target_bin = '/example/do_stuff_fuzzer'
    self.test_target = fuzz_target.FuzzTarget(self.fuzz_target_bin, 100,
                                              '/example/outdir', 'example')

  def test_valid_crash(self):
    """Tests that a valid crash returns True."""
    with unittest.mock.patch('fuzz_target.FuzzTarget.is_reproducible',
                             side_effect=[(True, True), (False, True)]):
      with tempfile.TemporaryDirectory() as tmp_dir:
        self.test_target.out_dir = tmp_dir
        self.assertTrue(
            self.test_target.is_crash_reportable('/example/crash/testcase'))

  # yapf: disable
  @parameterized.parameterized.expand([
      # Reproducible on PR build, but also reproducible on OSS-Fuzz.
      ([(True, True), (True, True)],),

      # Not reproducible on PR build, but somehow reproducible on OSS-Fuzz.
      # Unlikely to happen in real world except if test is flaky.
      ([(False, True), (True, False)],),

      # Not reproducible on PR build, and not reproducible on OSS-Fuzz.
      ([(False, True), (False, True)],),
  ])
  # yapf: enable
  def test_invalid_crash(self, is_reproducible_retvals):
    """Tests that an invalid crash causes the method to return False."""
    self.setUpPyfakefs()
    self.fs.create_file(self.fuzz_target_bin)
    self.fs.add_real_directory(TEST_FILES_PATH)
    with unittest.mock.patch('fuzz_target.FuzzTarget.is_reproducible',
                             side_effect=is_reproducible_retvals):
      oss_fuzz_build_path = '/oss-fuzz-build'

      with unittest.mock.patch('fuzz_target.FuzzTarget.download_oss_fuzz_build',
                               return_value=oss_fuzz_build_path):
        self.assertFalse(
            self.test_target.is_crash_reportable('/example/crash/testcase'))


class GetLatestBuildVersionUnitTest(unittest.TestCase):
  """Test the get_latest_build_version function in the fuzz_target module."""

  def test_get_valid_project(self):
    """Tests that the latest build can be retrieved from GCS."""
    test_target = fuzz_target.FuzzTarget('/example/path', 10, '/example/outdir',
                                         'example')
    latest_build = test_target.get_lastest_build_version()
    self.assertIsNotNone(latest_build)
    self.assertTrue(latest_build.endswith('.zip'))
    self.assertTrue('address' in latest_build)

  def test_get_invalid_project(self):
    """Tests that the latest build will return None when project doesn't
    exist."""
    test_target = fuzz_target.FuzzTarget('/example/path', 10, '/example/outdir',
                                         'not-a-proj')
    self.assertIsNone(test_target.get_lastest_build_version())
    test_target = fuzz_target.FuzzTarget('/example/path', 10, '/example/outdir')
    self.assertIsNone(test_target.get_lastest_build_version())


class DownloadOSSFuzzBuildDirIntegrationTests(unittest.TestCase):
  """Test the download_oss_fuzz_build in function in the fuzz_target module."""

  def test_single_download(self):
    """Tests that the build directory was only downloaded once."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      test_target = fuzz_target.FuzzTarget('/example/do_stuff_fuzzer', 10,
                                           tmp_dir, 'example')
      latest_version = test_target.get_lastest_build_version()
      with unittest.mock.patch(
          'fuzz_target.FuzzTarget.get_lastest_build_version',
          return_value=latest_version) as mock_build_version:
        for _ in range(5):
          oss_fuzz_build_path = test_target.download_oss_fuzz_build()
        self.assertEqual(1, mock_build_version.call_count)
        self.assertIsNotNone(oss_fuzz_build_path)
        self.assertTrue(os.listdir(oss_fuzz_build_path))

  def test_get_valid_project(self):
    """Tests the latest build can be retrieved from GCS."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      test_target = fuzz_target.FuzzTarget('/example/do_stuff_fuzzer', 10,
                                           tmp_dir, 'example')
      oss_fuzz_build_path = test_target.download_oss_fuzz_build()
      self.assertIsNotNone(oss_fuzz_build_path)
      self.assertTrue(os.listdir(oss_fuzz_build_path))

  def test_get_invalid_project(self):
    """Tests the latest build will return None when project doesn't exist."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      test_target = fuzz_target.FuzzTarget('/example/do_stuff_fuzzer', 10,
                                           tmp_dir)
      self.assertIsNone(test_target.download_oss_fuzz_build())
      test_target = fuzz_target.FuzzTarget('/example/do_stuff_fuzzer', 10,
                                           tmp_dir, 'not-a-proj')
      self.assertIsNone(test_target.download_oss_fuzz_build())

  def test_invalid_build_dir(self):
    """Tests the download will return None when out_dir doesn't exist."""
    test_target = fuzz_target.FuzzTarget('/example/do_stuff_fuzzer', 10,
                                         'not/a/dir', 'example')
    self.assertIsNone(test_target.download_oss_fuzz_build())


class DownloadAndUnpackZipUnitTests(unittest.TestCase):
  """Test the download and unpack functionality in the fuzz_target module."""

  def test_bad_zip_download(self):
    """Tests download_and_unpack_zip returns none when a bad zip is passed."""
    with tempfile.TemporaryDirectory() as tmp_dir, unittest.mock.patch(
        'urllib.request.urlretrieve', return_value=True):
      file_handle = open(os.path.join(tmp_dir, 'url_tmp.zip'), 'w')
      file_handle.write('Test file.')
      file_handle.close()
      self.assertIsNone(
          fuzz_target.download_and_unpack_zip('/not/a/real/url', tmp_dir))


if __name__ == '__main__':
  unittest.main()
