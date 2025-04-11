from typing import Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field, field_serializer

from rustic_ai.core.utils.basic_class_utils import get_class_from_name

ET = TypeVar("ET", bound=BaseModel)


class ClassifyRequest(BaseModel):
    source_text: str
    categories: List[str]
    instructions: Optional[str] = Field(None)


class ExtractionSpec(BaseModel):
    pydantic_model_to_extract: str
    extraction_instructions: Optional[str] = Field(None)

    _resolved_class: Optional[BaseModel] = None

    @property
    def extraction_class(self) -> Optional[BaseModel]:
        if self._resolved_class is None:
            self._resolved_class = get_class_from_name(self.pydantic_model_to_extract)  # type: ignore
        return self._resolved_class


class ExtractRequest(BaseModel):
    source_text: str
    extraction_spec: ExtractionSpec


class ClassifyAndExtractRequest(BaseModel):
    source_text: str
    categories_extractions_map: Dict[str, ExtractionSpec]
    classification_instructions: Optional[str] = Field(None)

    @property
    def categories(self) -> List[str]:
        return list(self.categories_extractions_map.keys())

    @property
    def extractions(self) -> List[ExtractionSpec]:
        return list(self.categories_extractions_map.values())

    def get_extraction_class_for_category(self, category: str) -> Optional[BaseModel]:
        if category not in self.categories_extractions_map:
            return None
        return self.categories_extractions_map[category].extraction_class

    def get_extraction_instructions_for_category(self, category: str) -> Optional[str]:
        if category not in self.categories_extractions_map:
            return None
        return self.categories_extractions_map[category].extraction_instructions


class ClassifyResponse(BaseModel):
    source_text: str
    category: str


class ExtractResponse(BaseModel, Generic[ET]):
    source_text: str
    extracted_data: List[ET]

    @field_serializer("extracted_data")
    def serialize_extractions(self, extracted_data: List[ET]):
        return [ed.model_dump() for ed in extracted_data]


class ClassifyAndExtractResponse(BaseModel, Generic[ET]):
    source_text: str
    category: str
    extracted_data: List[ET]

    @field_serializer("extracted_data")
    def serialize_extracted_data(self, extracted_data: List[ET]):
        return [ed.model_dump() for ed in extracted_data]
