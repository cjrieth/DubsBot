from typing import IO, AsyncGenerator, Union
import re
import json

from azure.ai.formrecognizer import DocumentTable
from azure.ai.formrecognizer.aio import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential

from .page import Page
from .parser import Parser
from .strategy import USER_AGENT
from bs4 import BeautifulSoup

class DocumentAnalysisHtmlParser(Parser):

    def __init__(
        self,
        endpoint: str,
        credential: Union[AsyncTokenCredential, AzureKeyCredential],
        model_id="prebuilt-layout",
        verbose: bool = False,
    ):
        self.model_id = model_id
        self.endpoint = endpoint
        self.credential = credential
        self.verbose = verbose

    async def parse(self, content: IO) -> AsyncGenerator[Page, None]:
        if self.verbose:
            print(f"Extracting text from '{content.name}' using Azure Document Intelligence")

        async with DocumentAnalysisClient(
            endpoint=self.endpoint, credential=self.credential, headers={"x-ms-useragent": USER_AGENT}
        ) as form_recognizer_client:
            poller = await form_recognizer_client.begin_analyze_document(model_id=self.model_id, document=content)
            form_recognizer_results = await poller.result()

            offset = 0
            for page_num, page in enumerate(form_recognizer_results.pages):

                yield Page(page_num=page_num, offset=offset, text=page.content)
        
class LocalHtmlParser(Parser):
    """
    Concrete parser that can parse the html representation of the UW Time Schedule.
    """

    async def parse(self, content: IO) -> AsyncGenerator[Page, None]:


        soup = BeautifulSoup(content, 'html.parser')
        try:
            with open("./data/"+ content.name[7:]  + ".1") as extra:
                # save catalog info
                additional_info = BeautifulSoup(extra, 'html.parser')
        except:
            # there is no catalog info for this major
            additional_info = None

        transformed_sched = "Spring 2024 Time Schedule\n\n"

        h2_tag = soup.h2
        if not h2_tag:
              # if page is not as expected (meaning no schedule) skip it
              yield Page(0, 0, "")
        else:

            transformed_sched += h2_tag.contents[0]
            transformed_sched += h2_tag.contents[2]

            # iterate through all of the class and section tables, adding them to the transformed string
            doc_tables = soup.find_all("table")
            last_class_name = ""
            for i in range(3, len(doc_tables)):
                if not doc_tables[i].pre:
                    # this is the start of a new class
                    j = 0
                    for string in doc_tables[i].stripped_strings:
                        if j == 0:
                            transformed_sched += "---------------------\n"
                            split_string = re.split("\s{2}", string)
                            transformed_sched += "Class: " + split_string[0] +  split_string[1]
                            class_name = split_string[0].lower().strip() + split_string[1].strip()
                            # # build json file of full major to abv name mappings
                            # with open("/workspaces/azure-search-openai-demo/scripts/prepdocslib/major_abv.json", "r+") as file:
                            #     major_dict = json.load(file)
                            #     major_dict[soup.title.get_text().lower()] = split_string[0]
                            #     file.seek(0)
                            #     json.dump(major_dict, file)
                        elif j == 1:
                            transformed_sched += " Name: " + string
                        elif j == 2:
                            if string[0] == '(':
                                transformed_sched += " Area of Knowledge:" + string + ", "
                            else:
                                transformed_sched += " Area of Kowledge: None, "
                        else:
                            transformed_sched += string
                        j = j + 1
                    if additional_info:
                        transformed_sched += "\n"
                        filter_catalog = additional_info.find_all("a", {"name": class_name})
                        if len(filter_catalog) > 0:
                            transformed_sched += "Course Description: " + filter_catalog[0].get_text()
                    transformed_sched += "\n\n"
                else:
                    # this is a section for the previous class
                    section_info = doc_tables[i].get_text()
                    if " QZ " not in section_info and " LB " not in section_info:
                        transformed_sched += "Main Section: "
                    elif  " QZ " in section_info :
                        transformed_sched += "Quiz Section: "
                    else:
                        transformed_sched += "Lab Section: "

                    regex_edit = re.findall("(?<!^) [M|T|W|Th|F]+[ ]+[0-9]", section_info)
                    regex_split =  re.split("(?<!^) [M|T|W|Th|F]+[ ]+[0-9]", section_info)
                    regex_final = regex_split[0]
                    expanded_string = ""
                    for j in range (len(regex_edit)):
                        regex_final += " Meeting Days:  "
                        for k in range(len(regex_edit[j])):
                            if regex_edit[j][k] == 'M':
                                expanded_string += "Monday,"
                            elif regex_edit[j][k] == 'T' and k != (len(regex_edit[j]) - 1) and regex_edit[j][k + 1] == 'h':
                                expanded_string += "Thursday,"
                            elif regex_edit[j][k] == 'T':
                                expanded_string += "Tuesday,"
                            elif regex_edit[j][k] == 'W':
                                expanded_string += "Wednesday,"
                            elif regex_edit[j][k] == 'F':
                                expanded_string += "Friday"
                        # last_piece = re.split("[a-zA-Z0-9\\-]+", regex_split[j + 1], maxsplit=1)
                        # last_piece2 = re.split("[a-zA-Z]+", regex_split[j + 1], maxsplit=1)
                        regex_final += expanded_string + "  Meeting Time: " + regex_edit[j][-1:] + regex_split[j + 1]
                        # if len(last_piece) > 1:
                        #     regex_final += " Meeting Room/Location: " + last_piece[1].strip()
                    transformed_sched += regex_final + "\n\n"

            # compress whitespace
            transformed_sched = re.sub("[ \t]+", " ", transformed_sched)

            # with open(h2_tag.contents[0] + '.txt', "w") as debug_output:
            #      debug_output.write(transformed_sched)

            yield Page(0, 0, transformed_sched)

    async def retrieve_major_mapping(self) -> dict:
        return self.major_mapping



            