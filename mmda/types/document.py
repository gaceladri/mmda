"""



"""

from abc import abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Type
import json
import os
from glob import glob

from mmda.types.image import Image
from mmda.types.document_elements import DocumentSymbols
from mmda.types.annotation import Annotation, DocSpanGroup, Indexer, DocSpanGroupIndexer
from mmda.types.names import Symbols, Images


@dataclass
class Document:

    DEFAULT_FIELDS = [Symbols, Images]

    def __init__(
        self,
        symbols: DocumentSymbols,
        images: Optional[List["Image.Image"]] = None,
    ):
        self.symbols = symbols
        self.images = images
        self._fields = self.DEFAULT_FIELDS
        self._indexers: Dict[str, Indexer] = {}

    @property
    def fields(self):
        return self._fields

    def _register_field(self, field_name):
        assert not field_name.startswith("_"), "The field_name should not start with `_`. "
        assert field_name not in self.fields, "This field name already exists"
        assert field_name not in ["fields"], "The field_name should not be 'fields'."           # TODO[kylel] whats this
        assert field_name not in dir(self), \
            f"The field_name should not conflict with existing class properties {field_name}"
        self._fields.append(field_name)
        self._indexers[field_name] = DocSpanGroupIndexer(num_pages=self.symbols.page_count)

    def _annotate(self, field_name, field_annotations):

        self._register_field(field_name)

        for annotation in field_annotations:
            annotation = annotation.annotate(self)

        setattr(self, field_name, field_annotations)

    def annotate(self, **annotations: List[Annotation]):
        """Annotate the fields for document symbols (correlating the annotations with the
        symbols) and store them into the papers.
        """
        for field_name, field_annotations in annotations.items():
            self._annotate(field_name, field_annotations)

    def _add(self, field_name, field_annotations):

        # This is different from annotate:
        # In add, we assume the annotations are already associated with the symbols
        # and the association is stored in the indexers. As such, we need to ensure 
        # that field and indexers have already been set in some way before calling 
        # this method. I am not totally sure how this mehtod would be used, but it 
        # is a reasonable assumption for now I believe. 

        assert field_name in self._fields
        assert field_name in self._indexers

        for annotation in field_annotations:
            assert annotation.doc == self
            # check that the annotation is associated with the document

        setattr(self, field_name, field_annotations)

    def add(self, **annotations: List[Annotation]):
        """Add document annotations into this document object.
        Note: in this case, the annotations are assumed to be already associated with
        the document symbols.
        """
        for field_name, field_annotations in annotations.items():
            self._add(field_name, field_annotations)

    def to_json(self, fields: Optional[List[str]] = None, with_images=False) -> Dict:
        """Returns a dictionary that's suitable for serialization

        Use `fields` to specify a subset of groups in the Document to include (e.g. 'sentences')
        If `with_images` is True, will also turn the Images into base64 strings.  Else, won't include them.

        Output format looks like
            {
                Symbols: ["...", "...", ...],

            }
        """
        fields = self.fields if fields is None else fields
        if not with_images:
            fields = [field for field in fields if field != Images]
        return {
            field: [group.to_json() for group in getattr(self, field)]
            for field in fields
        }

    def save(
        self,
        path: str,
        fields: Optional[List[str]] = None,
        with_images=True,
        images_in_json=False,
    ):

        if with_images and not images_in_json:
            assert os.path.isdir(
                path
            ), f"When with_images={with_images} and images_in_json={images_in_json}, it requires the path to be a folder"
            # f-string equals like f"{with_images=}" will break the black formatter and won't work for python < 3.8

        doc_json = self.to_json(fields, with_images=with_images and images_in_json)

        if with_images and not images_in_json:
            json_path = os.path.join(path, "document.json")     # TODO[kylel]: avoid hard-code

            with open(json_path, "w") as fp:
                json.dump(doc_json, fp)

            for pid, image in enumerate(self.images):
                image.save(os.path.join(path, f"{pid}.png"))
        else:
            with open(path, "w") as fp:
                json.dump(doc_json, fp)

    @classmethod
    def from_json(cls, doc_dict: Dict):
        fields = doc_dict.keys()        # TODO[kylel]: this modifies the referenced dict, not copy

        # instantiate Document
        symbols = fields.pop(Symbols)
        images = doc_dict.pop(Images, None)
        doc = cls(symbols=symbols, images=images)

        # TODO: unclear if should be `annotations` or `annotation` for `load()`
        for field_name, field_annotations in doc_dict.items():
            field_annotations = [
                DocumentSymbols.load(field_name=field_name, annotations=field_annotation, document=doc)
                for field_annotation in field_annotations
            ]
            doc._add(
                field_name, field_annotations
            )  # We should use add here as they are already annotated

        return doc

    @classmethod
    def load(cls, path: str) -> "Document":
        """Instantiate a Document object from its serialization.
        If path is a directory, loads the JSON for the Document along with all Page images
        If path is a file, just loads the JSON for the Document, assuming no Page images"""
        if os.path.isdir(path):
            json_path = os.path.join(path, "document.json")
            image_files = glob(os.path.join(path, "*.png"))
            image_files = sorted(
                image_files, key=lambda x: int(os.path.basename(x).replace('.png', ''))
            )
            images = [Image.load(image_file) for image_file in image_files]
        else:
            json_path = path
            images = None

        with open(json_path, "r") as fp:
            json_data = json.load(fp)

        doc = cls.from_json(json_data)
        doc.images = images

        return doc

    @classmethod
    def find(self, query: DocSpanGroup, field_name: str):

        # As for now query only supports for DocSpanGroup, the function is 
        # just this simple

        return self._indexers[field_name].index(query)