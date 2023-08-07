import os
import sys
import io
import uuid
from datetime import datetime, timedelta
import pathlib
import json
import typesense


curr_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(1, os.path.abspath(os.path.join(curr_dir, os.pardir)))
sys.path.append("../common-objects")
sys.path.append("../common-functions")
sys.path.append("../base-classes")
from aiwhisprBaseClasses import vectorDb

import aiwhisprConstants 

import logging

class createVectorDb(vectorDb):

    def __init__(self,vectordb_hostname,vectordb_portnumber, vectordb_key, content_site_name:str,src_path:str,src_path_for_results:str):
        vectorDb.__init__(self,
                          vectordb_hostname = vectordb_hostname,
                          vectordb_portnumber = vectordb_portnumber, 
                          vectordb_key = vectordb_key, 
                          content_site_name = content_site_name,
                          src_path = src_path,
                          src_path_for_results = src_path_for_results)
        self.vectorDbClient:typesense.Client
        self.logger = logging.getLogger(__name__)

    def connect(self):
        try:
            self.logger.debug("Creating a Typesense Connection")

            self.vectorDbClient = typesense.Client({
                'api_key': self.vectordb_key,
                'nodes': [
                    {
                    'host': self.vectordb_hostname,
                    'port': self.vectordb_portnumber,
                    'protocol': 'http'
                    },
            ],
            'connection_timeout_seconds': 60
            })
        except:
            self.logger.error("Could not create typesense connection to Typesense Server hostname: %s , portnumber: %s", self.vectordb_hostname, self.vectordb_portnumber)
        else:
            all_collections = self.vectorDbClient.collections.retrieve()
            table_found = "N"
            for collection in all_collections:
                if collection['name'] == 'content_chunk_map':
                    table_found = "Y"
            
            if table_found == "Y":
                self.logger.info("Typesense collection content_chunk_map already exists")
            else:
                self.logger.info("Typesense collection content_chunk_map does not exist , so we will create it")
                #create the collection in typesense
                #We are not creating an 'id' (unique id)  field. It will be provided in insert statements by the client
                #We expect id to be in the format <site-name>/<extracted-file_directory-name>/<chunk-files-directory>/<chunk-id>
                create_response = self.vectorDbClient.collections.create({
                    "name": "content_chunk_map",
                    "fields": [
                #SITE_NAME IS USED TO DEFINE THE SITE e.g. mas.gov.sg. THIS IS USED AS  FILTERING CRITERIA WHEN YOU WANT TO SEPRATE SEARCH BASED ON DIFFERENT SITES
                        {"name": "content_site_name", "type": "string", "index": True  },
                        #SRC_PATH IS USED TO DEFINE THE TOP SOURCE PATH FROM WHICH THE CONTENT RETRIEVER WILL START INDEXING CONTENT.
                        # Example: For an Azure Blob/container it will be https://<storage_account>.blob.core.windows.net/<container>
                        {"name": "src_path", "type": "string" , "optional": True, "index": False},
                        #SRC_PATH_FOR_RESULTS is used as the prefix instead of SRC_PATH when displaying the link to content in the search results
                        # Example: SRC_PATH for Azure Blob/container https://<storage_account>.blob.core.windows.net/<container>
                        # The results can have fileshare prefix SRC_PATH_FOR_RESULTS for Azure Blob/container https://<storage_account>.file.core.windows.net/<container>
                        {"name": "src_path_for_results", "type": "string", "optional": True, "index": False},
                        # CONTENT_PATH is the path to the original content including file name under the SRC_PATH
                        {"name": "content_path", "type": "string", "index": True},
                        # LAST_EDIT_DATE is the last edit date read from source for the content
                        {"name": "last_edit_date", "type": "float" , "optional": True, "index": False},
                        # TAGS is an optional field that is used to store any tags associated with the content , seprated by "|" character
                        {"name": "tags", "type": "string", "optional": True , "index": False},
                        # TITLE is an optional field that is used to store any title for the content
                        {"name": "title", "type": "string","optional": True, "index": True },
                        # CHUNK_TEXT  is the text that will be used by the LLM
                        {"name": "text_chunk", "type": "string", "optional": True , "index": False},
                        # CHUNK_NO is a mandatory field, it is a running sequence of numbers for the sections of the text in the document. This is useful when the content is broken into sections.
                        {"name": "text_chunk_no", "type": "int32", "optional": True, "index": False },
                        #BELOW VECTOR FIELD : We are chossing a 768 dimension vector based on all_mpnet
                        {"name": "vector_embedding", "type": "float[]", 'num_dim': 768, "optional": True , "index": True},
                        # VECTOR_EMBEDDING_DATE is the last date  on which this content LLM Vector was created
                        {"name": "vector_embedding_date", "type": "float" , "optional": True, "index": False},
                    ]

                })

                self.logger.info("Create Collection : %s", json.dumps(create_response))

    def insert(self, id:str,
               text_chunk_file_path:str, 
               content_path:str, 
               last_edit_date:float, 
               tags:str, 
               title:str, 
               text_chunk:str, 
               text_chunk_no:int, 
               vector_embedding:[]
               ):
        #Lets read the chuk file first
        text_chunk = ''
        try:
            with open(text_chunk_file_path) as f:
                text_chunk = f.readlines()
        except:
            self.logger.error("Could not read the text chunk file %s", text_chunk_file_path)
        else:
            try:
                ##Insert record in typesense collection
                content_chunk_map_record = {
                    'id' :  id,
                    'content_site_name' : self.content_site_name,
                    'src_path' : self.src_path,
                    'src_path_for_results' : self.src_path_for_results,
                    'content_path' : content_path,
                    'last_edit_date' : last_edit_date,
                    'tags' : tags,
                    'title' : title,
                    'text_chunk' : text_chunk,
                    'text_chunk_no' : text_chunk_no,
                    'vector_embedding' : vector_embedding
                }
                self.vectorDbClient.collections['content_chunk_map'].documents.create(content_chunk_map_record)
            except:
                self.logger.error("Could not insert the record in typesense")
                self.logger.error(json.dumps(content_chunk_map_record))

    def deleteAll(self):
        #delete all rows for the content_site_name 
        filter_by_conditions = 'content_site_name:=' + self.content_site_name
        search_parameters= {
            'q': self.content_site_name,
            'query_by': 'content_site_name',
            'include_fields': 'content_path',
            'filter_by':filter_by_conditions
        }
        try:
            response_del = self.vectorDbClient.collections['content_chunk_map'].documents.delete(search_parameters)
            self.logger.debug("Deleted rows from content_chunk_map")   
            self.logger.debug(json.dumps(response_del))
        except: 
            self.logger.error("Could not deleteAll for content_chunk_map")   
            self.logger.erro(json.dumps(search_parameters))
            
