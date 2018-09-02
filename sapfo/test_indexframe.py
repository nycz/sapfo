import unittest
from unittest import mock

from PyQt4 import QtGui

import indexframe

class IndexFrameTest(unittest.TestCase):

    @mock.patch('indexframe.set_hotkey')
    def setUp(self, mock_hotkey):
        app = QtGui.QApplication([])
        self.testobject = indexframe.IndexFrame(None, False)

    @mock.patch('indexframe.IndexFrame.regenerate_visible_entries')
    @mock.patch('indexframe.IndexFrame.refresh_view')
    @mock.patch('indexframe.IndexFrame.error')
    @mock.patch('indexframe.IndexFrame.print_')
    def test_filter_reset(self, mock_print, mock_error, mock_refresh_view,
                          mock_regen_visible_entries):
        mock_regen_visible_entries.return_value = ()
        # Empty filters, no change
        self.testobject.visible_entries = ()
        self.testobject.filter_entries('')
        mock_print.emit.assert_called_with('Filters reset')
        self.assertFalse(mock_error.emit.called)
        self.assertFalse(mock_refresh_view.called)
        # Empty filters
        self.testobject.visible_entries = (1,2,3)
        self.testobject.filter_entries('')
        mock_print.emit.assert_called_with('Filters reset')
        self.assertFalse(mock_error.emit.called)
        self.assertTrue(mock_refresh_view.called)


    @mock.patch('indexframe.IndexFrame.regenerate_visible_entries')
    @mock.patch('indexframe.IndexFrame.refresh_view')
    @mock.patch('indexframe.IndexFrame.error')
    @mock.patch('indexframe.IndexFrame.print_')
    def test_filter_nothing_to_remove(self, mock_print, mock_error,
                                      mock_refresh_view,
                                      mock_regen_visible_entries):
        self.testobject.active_filters = ()
        self.testobject.filter_entries('-')
        # Asserts
        mock_error.emit.assert_called_with('No filter to remove')
        self.assertFalse(mock_regen_visible_entries.called)
        self.assertFalse(mock_print.emit.called)
        self.assertFalse(mock_refresh_view.called)


    @mock.patch('indexframe.IndexFrame.regenerate_visible_entries')
    @mock.patch('indexframe.IndexFrame.refresh_view')
    @mock.patch('indexframe.IndexFrame.error')
    @mock.patch('indexframe.IndexFrame.print_')
    def test_filter_remove(self, mock_print, mock_error, mock_refresh_view,
                           mock_regen_visible_entries):
        self.testobject.entries = (4,5,6,7,8,9,10,11)
        self.testobject.visible_entries = (4,5,6,7,8)
        mock_regen_visible_entries.return_value = (4,5,6,7,8,9)
        self.testobject.active_filters = (1,2,3)
        self.testobject.filter_entries('-')
        # Asserts
        self.assertEqual(self.testobject.active_filters, (1,2))
        printstr = 'Last filter removed: {}/{} entries visible'.format(6,8)
        mock_print.emit.assert_called_with(printstr)
        self.assertTrue(mock_regen_visible_entries.called)
        self.assertFalse(mock_error.emit.called)
        self.assertTrue(mock_refresh_view.called)


if __name__ == '__main__':
    unittest.main()