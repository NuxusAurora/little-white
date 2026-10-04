import ctypes
import unittest
from unittest.mock import Mock, patch

import desktop_icons
import pet


class RegressionTests(unittest.TestCase):
    def test_required_heart_sprite_exists(self):
        self.assertIsNotNone(pet._find_sprite('heart'))

    def test_disabled_mode_rejects_kicks(self):
        puppy = pet.Pet.__new__(pet.Pet)
        puppy._kick_enabled = False
        with patch.object(desktop_icons, 'icon_screen_positions') as read:
            self.assertFalse(puppy._kick_icon_physics(0, 10, 10))
        read.assert_not_called()

    def test_failed_grid_disable_prevents_flight(self):
        puppy = pet.Pet.__new__(pet.Pet)
        puppy._kick_enabled = True
        puppy._icon_fly = puppy._icon_return = puppy._icon_carry = None
        puppy._icon_homes = {}
        puppy._snap_was_on = False
        with patch.object(desktop_icons, 'icon_screen_positions', return_value={0: (100, 200)}), \
                patch.object(desktop_icons, 'get_folder_flags', return_value=desktop_icons.FWF_SNAPTOGRID), \
                patch.object(desktop_icons, 'set_snap_grid', return_value=False), \
                patch.object(pet, '_dbg'):
            self.assertFalse(puppy._kick_icon_physics(0, 10, 10))
        self.assertIsNone(puppy._icon_fly)

    def test_variant_layout_matches_windows_abi(self):
        self.assertEqual(ctypes.sizeof(desktop_icons.VARIANT),
                         24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 16)

    def test_test_mode_never_touches_desktop(self):
        puppy = pet.Pet.__new__(pet.Pet)
        puppy.test_mode = True
        puppy.root = Mock()
        puppy._ensure_icon_homes = Mock()
        puppy._kick_desktop_icons()
        puppy._ensure_icon_homes.assert_not_called()
        puppy.root.after.assert_not_called()

    def test_failed_snap_restore_remains_retryable(self):
        puppy = pet.Pet.__new__(pet.Pet)
        puppy._icon_fly = puppy._icon_return = puppy._icon_carry = None
        puppy._snap_was_on = True
        with patch.object(desktop_icons, 'set_snap_grid', return_value=False):
            puppy._maybe_restore_snap()
        self.assertTrue(puppy._snap_was_on)

    def test_shutdown_stops_worker_then_restores_touched_icon(self):
        puppy = pet.Pet.__new__(pet.Pet)
        puppy._icon_phys_stop = __import__('threading').Event()
        puppy._icon_phys_thread = Mock()
        puppy._icon_phys_thread.is_alive.return_value = False
        puppy._icon_fly = {'index': 7, 'home': (100, 200)}
        puppy._icon_return = puppy._icon_carry = None
        puppy._snap_was_on = True
        with patch.object(desktop_icons, 'move_icon', return_value=True) as move, \
                patch.object(desktop_icons, 'set_snap_grid', return_value=True) as snap:
            puppy._cleanup_icons()
        self.assertTrue(puppy._icon_phys_stop.is_set())
        move.assert_called_once_with(7, 100, 200)
        snap.assert_called_once_with(True)


if __name__ == '__main__':
    unittest.main()
