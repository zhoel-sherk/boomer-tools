# Profile Settings - separate config for Clean and Merge
# This file stores per-profile settings for Clean and Merge functionality

import os
import configparser

DEFAULT_SETTINGS = {
    # Clean settings
    'resistor_include_tolerance': 'true',
    'resistor_include_package': 'true',
    'resistor_custom_regex': '',
    'cap_include_voltage': 'true',
    'cap_include_dielectric': 'true',
    'cap_custom_regex': '',
    'other_custom_regex': '',
    # Merge settings
    'merge_delete_dnp': 'false',
    'merge_coord_units': 'mils',
}

class ProfileSettings:
    """Manages clean and merge settings per profile"""
    
    def __init__(self, profile_name: str):
        self.profile_name = profile_name
        self.config = configparser.ConfigParser()
        self.config_file = self._get_config_file()
        self.load()
    
    def _get_config_file(self) -> str:
        """Get config file path based on profile name"""
        config_dir = os.path.expanduser("~/.boomer")
        os.makedirs(config_dir, exist_ok=True)
        # Sanitize profile name for filename
        safe_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in self.profile_name)
        return os.path.join(config_dir, f"settings_{safe_name}.ini")
    
    def load(self):
        """Load settings from file"""
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
            if not self.config.has_section('clean'):
                self.config.add_section('clean')
            if not self.config.has_section('merge'):
                self.config.add_section('merge')
        else:
            self.config.add_section('clean')
            self.config.add_section('merge')
            for key, value in DEFAULT_SETTINGS.items():
                if 'clean' in key:
                    self.config.set('clean', key, value)
                else:
                    self.config.set('merge', key, value)
    
    def save(self):
        """Save settings to file"""
        with open(self.config_file, 'w') as f:
            self.config.write(f)
    
    def get(self, key: str, default: str = '') -> str:
        """Get setting value"""
        section = 'clean' if 'clean' in key else 'merge'
        return self.config.get(section, key, fallback=default)
    
    def set(self, key: str, value: str):
        """Set setting value"""
        section = 'clean' if 'clean' in key else 'merge'
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, value)
    
    # Clean settings
    @property
    def resistor_include_tolerance(self) -> bool:
        return self.get('resistor_include_tolerance', 'true').lower() == 'true'
    
    @resistor_include_tolerance.setter
    def resistor_include_tolerance(self, value: bool):
        self.set('resistor_include_tolerance', str(value).lower())
    
    @property
    def resistor_include_package(self) -> bool:
        return self.get('resistor_include_package', 'true').lower() == 'true'
    
    @resistor_include_package.setter
    def resistor_include_package(self, value: bool):
        self.set('resistor_include_package', str(value).lower())
    
    @property
    def resistor_custom_regex(self) -> str:
        return self.get('resistor_custom_regex', '')
    
    @resistor_custom_regex.setter
    def resistor_custom_regex(self, value: str):
        self.set('resistor_custom_regex', value)
    
    @property
    def cap_include_voltage(self) -> bool:
        return self.get('cap_include_voltage', 'true').lower() == 'true'
    
    @cap_include_voltage.setter
    def cap_include_voltage(self, value: bool):
        self.set('cap_include_voltage', str(value).lower())
    
    @property
    def cap_include_dielectric(self) -> bool:
        return self.get('cap_include_dielectric', 'true').lower() == 'true'
    
    @cap_include_dielectric.setter
    def cap_include_dielectric(self, value: bool):
        self.set('cap_include_dielectric', str(value).lower())
    
    @property
    def cap_custom_regex(self) -> str:
        return self.get('cap_custom_regex', '')
    
    @cap_custom_regex.setter
    def cap_custom_regex(self, value: str):
        self.set('cap_custom_regex', value)
    
    @property
    def other_custom_regex(self) -> str:
        return self.get('other_custom_regex', '')
    
    @other_custom_regex.setter
    def other_custom_regex(self, value: str):
        self.set('other_custom_regex', value)
    
    # Merge settings
    @property
    def merge_delete_dnp(self) -> bool:
        return self.get('merge_delete_dnp', 'false').lower() == 'true'
    
    @merge_delete_dnp.setter
    def merge_delete_dnp(self, value: bool):
        self.set('merge_delete_dnp', str(value).lower())
    
    @property
    def merge_coord_units(self) -> str:
        return self.get('merge_coord_units', 'mils')
    
    @merge_coord_units.setter
    def merge_coord_units(self, value: str):
        self.set('merge_coord_units', value)


# Global instance
_profile_settings = {}

def get_profile_settings(profile_name: str) -> ProfileSettings:
    """Get or create profile settings"""
    if profile_name not in _profile_settings:
        _profile_settings[profile_name] = ProfileSettings(profile_name)
    return _profile_settings[profile_name]
