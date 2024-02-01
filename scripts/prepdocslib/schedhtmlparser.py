from typing import IO, AsyncGenerator

from .page import Page
from .parser import Parser
from bs4 import BeautifulSoup
from bs4.element import Comment



class HtmlParser(Parser):
    """
    Concrete parser that can parse the html representation of the UW Time Schedule.
    """

    async def parse(self, content: IO) -> AsyncGenerator[Page, None]:
        offset = 0
        soup = BeautifulSoup(content, 'html.parser')

        transformed_sched = "Spring 2024 Time Schedule\n\n"

        h2_tag = soup.h2
        transformed_sched += h2_tag.contents[0]
        transformed_sched += h2_tag.contents[2]
        transformed_sched += "\n\nBelow is is a list of all classes for this major and their associated sections: \n\n"

        print()

        # iterate through all of the class and section tables, adding them to the transformed string
        doc_tables = soup.find_all("table")

        for i in range(3, len(doc_tables)):
            if not doc_tables[i].pre:
                # this is the start of a new class
                j = 0
                for string in doc_tables[i].stripped_strings:
                    if j == 0:
                        transformed_sched += "Class: " + string.split(" ")[0] + ", Level: " + string.split(" ")[1]
                    elif j == 1:
                        transformed_sched += ", Name: " + string
                    elif j == 2:
                        if string[0] == '(':
                            transformed_sched += ", Area of Knowledge: " + string + ", "
                        else:
                            transformed_sched += ", Area of Knowledge: None, "
                    else:
                        transformed_sched += string
                    j = j + 1
                transformed_sched += "\n"
            else:
                # this is a section for the previous class
                section_info = doc_tables[i].get_text()
                if " QZ " not in section_info:
                    transformed_sched += "Main Section: "
                else:
                    transformed_sched += "Quiz Section: "
                transformed_sched += section_info + "\n"
            
        yield Page(0, 0, transformed_sched)
            