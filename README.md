# DubsBot | The Unoffical UW Course Schedule Chatbot 🐾


## Table of Contents

- [Features](#features)
- [Assistant Strengths](#assistant-strengths)
- [How it works](#how-it-works)
- [Limitations](#limitations)
- [Future Additions](#future-additions)


This is the home for DubsBot, a chatbot designed to assist University of Washington students in learning about available classes and planning their course schedules. This project was created for the [Microsoft Azure AI Chat Hackathon](https://github.com/microsoft/AI-Chat-App-Hack).

This assistant is a RAG (Retrieval Augmented Generation) chat application, it has been specially optimized and trained to utilize available UW Time Schedules.

## Features 💫

* Chat about class offerings for Spring Quarter 2024
* Compare topics, times, and instructors for courses
* Find course offerings that fit your interests or build off of previous classes
* See how course offerings fit with general degree requirments

## Assistant Strengths 💪

DubsBot excels at digesting course information and providing recomendations based of off user interests or goals. Its structure as a converstational experience allows for clarifying questions and context based answers.

Students can expect the assistant to be very helpful in providing 

### Example queries

* Are there music theory classes availible for non majors?
* What are some CSE classes about AI?
* I just took ____ and want to continue learning ____, what should I take?

## How it works ⚙️

### Data Ingestion

There are multiple steps for proper data ingestion:

#### Web Scraping

There are two provided Bash web scraping scripts, these scipts use Lynx: 
* `/scripts/scrapeschedules.sh` for scraping the courses on offer for Spring 2024
* `/scripts/scrapecatalog.sh` for scraping the course catalogs for each department

**IMPORTANT:** For proper data structure, `scrapeschedules.sh` must first be run to completion before running `scrapecatalog.sh`

These scripts will populate the `/data/` directory will all necessary data. 

The script `/data/prune.sh` is a utility script to remove all time schedules and course catalogs that are missing their complements, it should be run after all data has been scraped to get rid of unecessary files.

#### HTML Parsing

Upon running `prepdocs.sh`, all HTML documents in the `/data` folder are parsed with a custom local parser. The HTML time schedules are translated into simple readable strings, where any abreviations are expanded, labels are given to different class sessions, and other course information is refined. The parser will also open the associated course catalog for each department's time schedule and insert a full course description for each course on offer for the quarter.

#### Search Index Chunking

Time schedule length can vary greatly between departments, and as a result all parsed time schedules must be chunked intelligently before being uploaded to the Azure Search Index. The custom text splitter will split the time schedules into chunks for each course that is offered, ensuring that all information for a single class stays together in the index.

### Azure Search Index Structure

A search index is created to store the parsed HTML files with additional fields to facilitate proper data retrieval. All individual classes are associated with a course level and department code within the index. This allows for structured queries during chat operation, and for proper filtering for appropiate classes.

### Chat Approach

This application implements the **read-retrieve-read** approach to interacting with GPT and the Azure Search Index. The original user query is sent to the LLM in order to extact specifc fields and choose a query type for the search index. The generated search query is then normalized and executed on the Azure Search Index with appropriate filtering. The results are sent back to the LLM for answer synthesis and displayed to the user.

### Prompt Engineering

DubsBot largely follows standard assistant behavior, save for its predisposition to bark.

## Limitations 🙅‍♂️

This application currently has some limitations that many impact its ability to help with all questions.

* Only course data for Spring 2024 is included in the index, and as a result the assistant cannot answer questions about past or future quarters. eg: "How often is CSE 333 offered?"
* The assitant cannot access student specific documents and information, so it cannot make choices based off of a student's previous course load without being told explicity what the student has taken while chatting. eg: "What classes should I take to fufill my Natural Sciences credits?"
* The assistant does not have access to internal UW course data, and as such cannot provide information on course trends, real time enrollment numbers, or unexpected changes to course offerings. eg: "How often is a CSE 143 totally filled?"
* The assistant cannot actually register students for courses, registraton must be done through MyPlan. 
* The assistant cannot see the entire search index at once, so it cannot answer questions about how many classes there are.

## Future Additions 🔮

* Allow for student supplied documents such as transcipts or existing course plans. This would allow the assistant to give personalized recommendations based on what classes the student is already planning to take, or which requirements they still need to fufill.
* Make data from past and future quarters available. This would allow the assistant to give information on class offerings in the past or planned for the near future. 
