from pydantic import BaseModel, Field
from typing import Dict

class SBOMStatusRow(BaseModel):
    """Represents a row from the SBOM status CSV file."""
    
    status: str
    product: str
    project: str
    last_pipeline: str
    test_fetched_sbom: str
    test_version: str
    test_readability: str
    test_well_formed: str
    test_emptiness: str
    dt_project: str
    dt_link: str
    
    # Store all other columns for context
    additional_data: Dict[str, str] = Field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'SBOMStatusRow':
        """Create SBOMStatusRow from dictionary."""
        # Extract known fields
        known_fields = {
            'status': data.get('Status', ''),
            'product': data.get('Product', ''),
            'project': data.get('Project', ''),
            'last_pipeline': data.get('Last pipeline', ''),
            'test_fetched_sbom': data.get('test_fetched_sbom', ''),
            'test_version': data.get('test_version', ''),
            'test_readability': data.get('test_readability', ''),
            'test_well_formed': data.get('test_well_formed', ''),
            'test_emptiness': data.get('test_emptiness', ''),
            'dt_project': data.get('DT project', ''),
            'dt_link': data.get('DT link', ''),
        }
        
        # Store all other columns as additional data
        additional = {k: v for k, v in data.items() if k not in [
            'Status', 'Product', 'Project', 'Last pipeline', 'test_fetched_sbom',
            'test_version', 'test_readability', 'test_well_formed', 'test_emptiness',
            'DT project', 'DT link'
        ]}
        
        known_fields['additional_data'] = additional
        return cls(**known_fields)
    
    def is_error(self) -> bool:
        """Check if this row has error status."""
        return 'error' in self.status.lower()
    
    def get_error_description(self) -> str:
        """Generate a detailed error description from the row data."""
        errors = []
        
        # Check test_fetched_sbom for specific errors
        if self.test_fetched_sbom is not None and 'ok' not in self.test_fetched_sbom.lower():
            errors.append(f"SBOM Fetch Issue: {self.test_fetched_sbom}")
        
        # Check other test fields
        test_fields = {
            'Version': self.test_version,
            'Readability': self.test_readability,
            'Well-formed': self.test_well_formed,
            'Emptiness': self.test_emptiness,
        }
        
        for test_name, test_value in test_fields.items():
            if test_value and 'ok' not in test_value:
                errors.append(f"{test_name} Test Failed: {test_value}")
        
        # Check additional data for errors
        for key, value in self.additional_data.items():
            if value and 'ok' not in str(value):
                errors.append(f"{key}: {value}")
        
        if not errors:
            errors.append("Status marked as error but no specific test failures found")
        
        return "\n".join(errors)
