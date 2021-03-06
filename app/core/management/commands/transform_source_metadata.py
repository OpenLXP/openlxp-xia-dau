import hashlib
import pandas as pd
import logging
from django.core.management.base import BaseCommand
from core.models import XIAConfiguration
from core.models import MetadataLedger
from django.utils import timezone
from core.management.utils.xsr_client import read_json_data

logger = logging.getLogger('dict_config_logger')


def get_target_metadata_for_transformation():
    """Retrieve target metadata schema from XIA configuration """
    logger.info("Configuration of schemas and files")
    xia_data = XIAConfiguration.objects.first()
    target_metadata_schema = xia_data.source_target_mapping
    logger.info("Reading schema for transformation")
    # Read source transformation schema as dictionary
    target_mapping_dict = read_json_data(target_metadata_schema)
    return target_mapping_dict


def get_source_metadata_for_transformation():
    """Retrieving Source metadata from MetadataLedger that needs to be
        transformed"""
    logger.info(
        "Retrieving source metadata from MetadataLedger that needs to be "
        "transformed")
    source_data_dict = MetadataLedger.objects.values(
        'source_metadata').filter(
        source_metadata_validation_status='Y',
        record_lifecycle_status='Active').exclude(
        source_metadata_validation_date=None)

    return source_data_dict


def create_target_metadata_dict(target_mapping_dict, source_data_dict):
    # Create dataframe using target metadata schema
    target_schema = pd.DataFrame.from_dict(
        target_mapping_dict,
        orient='index')
    # Updating null values with empty strings for replacing metadata
    source_data_dict = {
        k: '' if not v else v for k, v in
        source_data_dict.items()}
    # Replacing metadata schema with mapped values from source metadata
    target_schema = target_schema.replace(
        source_data_dict)
    # Dropping index value and creating json object
    target_data = target_schema.apply(lambda x: [x.dropna()],
                                      axis=1).to_json()
    # Creating dataframe from json object
    target_data_df = pd.read_json(target_data)
    # transforming target dataframe to dictionary object for replacing
    # values in target with new value
    target_data_dict = target_data_df.to_dict(orient='index')
    return target_data_dict


def replace_field_on_target_schema(ind1, target_section_name,
                                   target_field_name,
                                   target_data_dict):
    """Replacing values in field referring target schema"""
    if target_field_name == 'EducationalContext':
        if target_data_dict[ind1][target_section_name][
            target_field_name] == 'y' or \
                target_data_dict[ind1][
                    target_section_name][
                    target_field_name] == 'Y':
            target_data_dict[ind1][
                target_section_name][
                target_field_name] = 'Mandatory'
        else:
            if target_data_dict[ind1][
                target_section_name][
                target_field_name] == 'n' or \
                    target_data_dict[ind1][
                        target_section_name][
                        target_field_name] == 'N':
                target_data_dict[ind1][
                    target_section_name][
                    target_field_name] = 'Non - ' \
                                         'Mandatory '


def store_transformed_source_metadata(key_value, key_value_hash,
                                      target_data_dict,
                                      hash_value):
    """Storing target metadata in MetadataLedger"""
    MetadataLedger.objects.filter(
        source_metadata_key=key_value,
        record_lifecycle_status='Active',
        source_metadata_validation_status='Y'
    ).update(
        source_metadata_transformation_date=timezone.now(),
        target_metadata_key=key_value,
        target_metadata_key_hash=key_value_hash,
        target_metadata=target_data_dict,
        target_metadata_hash=hash_value)


def transform_source_using_key(source_data_dict, target_mapping_dict):
    """Transforming source data using target metadata schema"""
    logger.info(
        "Transforming source data using target renaming and mapping "
        "schemas and storing in json format")
    len_source_metadata = len(source_data_dict)
    for ind in range(len_source_metadata):
        for table_column_name in source_data_dict[ind]:
            # Create dataframe using target metadata schema

            target_data_dict = create_target_metadata_dict(target_mapping_dict,
                                                           source_data_dict
                                                           [ind]
                                                           [table_column_name])
            # Looping through target values in dictionary
            for ind1 in target_data_dict:
                for target_section_name in target_data_dict[ind1]:
                    for target_field_name in target_data_dict[ind1][
                         target_section_name]:
                        # Replacing values in field referring target schema
                        replace_field_on_target_schema(ind1,
                                                       target_section_name
                                                       , target_field_name,
                                                       target_data_dict)
                        # Create key_hash value to
                        if target_field_name == 'CourseCode' or \
                                'CourseProviderName':
                            key_course = target_data_dict[ind1][
                                target_section_name].get(
                                'CourseCode')
                            key_source = target_data_dict[ind1][
                                target_section_name].get(
                                'CourseProviderName')
                            if key_source:
                                if key_course:
                                    key_value = '_'.join(
                                        [key_source, key_course])

                key_value_hash = hashlib.md5(
                    key_value.encode('utf-8')).hexdigest()

                hash_value = hashlib.md5(
                    str(target_data_dict[ind1]).encode(
                        'utf-8')).hexdigest()
                store_transformed_source_metadata(key_value, key_value_hash,
                                                  target_data_dict[ind1],
                                                  hash_value)


class Command(BaseCommand):
    """Django command to extract data in the Experience index Agent (XIA)"""

    def handle(self, *args, **options):
        """
            Metadata is transformed in the XIA and stored in Metadata Ledger
        """
        target_mapping_dict = get_target_metadata_for_transformation()
        source_data_dict = get_source_metadata_for_transformation()
        transform_source_using_key(source_data_dict, target_mapping_dict)

        logger.info('MetadataLedger updated with transformed data in XIA')
