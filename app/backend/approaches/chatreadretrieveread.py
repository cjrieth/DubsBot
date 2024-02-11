from typing import Any, Coroutine, List, Literal, Optional, Union, overload
import json
import re

from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorQuery
from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionToolParam,
)

from approaches.approach import ThoughtStep
from approaches.chatapproach import ChatApproach
from core.authentication import AuthenticationHelper
from core.modelhelper import get_token_limit


class ChatReadRetrieveReadApproach(ChatApproach):
    """
    A multi-step approach that first uses OpenAI to turn the user's question into a search query,
    then uses Azure AI Search to retrieve relevant documents, and then sends the conversation history,
    original user question, and search results to OpenAI to generate a response.
    """

    def __init__(
        self,
        *,
        search_client: SearchClient,
        auth_helper: AuthenticationHelper,
        openai_client: AsyncOpenAI,
        chatgpt_model: str,
        chatgpt_deployment: Optional[str],  # Not needed for non-Azure OpenAI
        embedding_deployment: Optional[str],  # Not needed for non-Azure OpenAI or for retrieval_mode="text"
        embedding_model: str,
        sourcepage_field: str,
        content_field: str,
        query_language: str,
        query_speller: str,
    ):
        self.search_client = search_client
        self.openai_client = openai_client
        self.auth_helper = auth_helper
        self.chatgpt_model = chatgpt_model
        self.chatgpt_deployment = chatgpt_deployment
        self.embedding_deployment = embedding_deployment
        self.embedding_model = embedding_model
        self.sourcepage_field = sourcepage_field
        self.content_field = content_field
        self.query_language = query_language
        self.query_speller = query_speller
        self.chatgpt_token_limit = get_token_limit(chatgpt_model)

    @property
    def system_message_chat_conversation(self):
        return """You assist students in planning their course schedules and degree goals. You are the friendly University of Washington school mascot, a Husky named Dubs. Act animated and behave like a dog.
        DO NOT answer questions about how many classes there are. Answer ONLY with the facts listed in the list of sources below. Always let the students know to check the official course offerings. Do not generate answers that don't use the sources below. If the question is very broad ask clarifying questions.
        For tabular information return it as an html table. Do not return markdown format. If the question is not in English, answer in the language used in the question.
        Each source has a name followed by colon and the actual information, always include the source name for each fact you use in the response. Use square brackets to reference the source, for example [info1.txt]. Don't combine sources, list each source separately, for example [info1.txt][info2.pdf].
        {follow_up_questions_prompt}
        {injected_prompt}
        """

    @overload
    async def run_until_final_call(
        self,
        history: list[dict[str, str]],
        overrides: dict[str, Any],
        auth_claims: dict[str, Any],
        should_stream: Literal[False],
    ) -> tuple[dict[str, Any], Coroutine[Any, Any, ChatCompletion]]: ...

    @overload
    async def run_until_final_call(
        self,
        history: list[dict[str, str]],
        overrides: dict[str, Any],
        auth_claims: dict[str, Any],
        should_stream: Literal[True],
    ) -> tuple[dict[str, Any], Coroutine[Any, Any, AsyncStream[ChatCompletionChunk]]]: ...

    async def run_until_final_call(
        self,
        history: list[dict[str, str]],
        overrides: dict[str, Any],
        auth_claims: dict[str, Any],
        should_stream: bool = False,
    ) -> tuple[dict[str, Any], Coroutine[Any, Any, Union[ChatCompletion, AsyncStream[ChatCompletionChunk]]]]:
        has_text = overrides.get("retrieval_mode") in ["text", "hybrid", None]
        has_vector = overrides.get("retrieval_mode") in ["vectors", "hybrid", None]
        use_semantic_captions = True if overrides.get("semantic_captions") and has_text else False
        top = overrides.get("top", 5)
        filter = self.build_filter(overrides, auth_claims)
        use_semantic_ranker = True if overrides.get("semantic_ranker") and has_text else False

        original_user_query = history[-1]["content"]
        user_query_request = "Generate search query for: " + original_user_query

        # TODO Modify class search to incorperate multiple major requests
        # TODO support quantatative queries? eg how many CSE classes are there

        tools: List[ChatCompletionToolParam] = [
            {
                "type": "function",
                "function": {
                    "name": "search_sources",
                    "description": "Retrieve sources from the Azure AI Search index",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_query": {
                                "type": "string",
                                "description": "Query string to retrieve documents from azure search eg: 'Health care plan'",
                            }
                        },
                        "required": ["search_query"],
                    },
                },
                "type": "function",
                "function": {
                    "name": "search_degree_requirements",
                    "description": "Answer quesions based off of degree requirements",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_query": {
                                "type": "string",
                                "description": "Query string to ask about degree requirements eg: 'What are the CSE degree requirements'",
                            }
                        },
                        "required": ["search_query"],
                    },
                },
                "type": "function",
                "function": {
                    "name": "filtered_search",
                    "description": "Filter search with more specific fields",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_query": {
                                "type": "string",
                                "description": "If the ask is related to a specific major and/or a specific level eg: 'Show me some 300 level cse classes' put the whole query here.",
                            },
                            "major": {
                                "type": "string",
                                "description": "If the ask is related to a specific majors eg: 'Plan me a schedule with 1 communications class and 1 anthropology class' set to a list of majors they are querying. Set to a list if there are multiple majors.",
                            },
                            "level": {
                                "type": "string",
                                "description": "If the ask contains the word level eg: 'Show me the details for 100 level classes' set to the level they are querying. ONLY set this if the word 'level' is explicitly stated in the message.",
                            },
                            "instructor": {
                                "type": "string",
                                "description": "If the ask is related to a specific instructor/professor/teacher eg: 'What CSE classes does Jane Doe teach?' set to the instructor they are querying.",
                            }
                        },
                        "required": ["search_query", "level", "major", "instructor"],
                    },
                },
            }
        ]

        # STEP 1: Generate an optimized keyword search query based on the chat history and the last question
        messages = self.get_messages_from_history(
            system_prompt=self.query_prompt_template,
            model_id=self.chatgpt_model,
            history=history,
            user_content=user_query_request,
            max_tokens=self.chatgpt_token_limit - len(user_query_request),
            few_shots=self.query_prompt_few_shots,
        )

        chat_completion: ChatCompletion = await self.openai_client.chat.completions.create(
            messages=messages,  # type: ignore
            # Azure Open AI takes the deployment name as the model name
            model=self.chatgpt_deployment if self.chatgpt_deployment else self.chatgpt_model,
            temperature=0.0,
            max_tokens=100,  # Setting too low risks malformed JSON, setting too high may affect performance
            n=1,
            tools=tools,
            tool_choice="auto",
        )

        query_text = self.get_search_query(chat_completion, original_user_query)

        # Good examples:
        # i just finished CSE 333 and I like operating systems, what should I take next
        # Can't do:
        # how often is CSE 333 offered
        # how often is a class filled
        
        # are there MUSIC theory classes for non majors

        use_full_search_mode = False
        if isinstance(query_text, dict):
            # update the filters to narrow down class by level
            level = query_text.get("level")
            majors = query_text.get("major")
            instructor = query_text.get("instructor")
            if level:
                # only do a level filter if it was specifically asked for
                if 'level' in query_text.get("search_query"):
                    try:
                        if not filter:
                            filter = "level ge " + str(level) + " and level lt " + str(int(level) + 100)
                        else:
                            filter += "and level ge " + str(level) + " and level lt " + str(level + 100)
                    except:
                        filter = None
            if majors:
                if not isinstance(majors, list):
                    majors = [majors]
                first_major = True
                for major in majors:
                    with open("./approaches/major_abv.json") as file:
                        abv_dict = json.load(file)
                        # switch to abrev
                        if major.lower() in abv_dict:
                            major = abv_dict[major.lower()]
                        # for key in sorted(abv_dict):
                        #     # need to fix when majors have similar names
                        #     if major.lower() in key: 

                        #         break
                    if not filter:
                        filter = "(major eq " + "'" + major.lower() + "'"
                        first_major = False
                    elif first_major:
                        filter += " and (major eq " + "'" + major.lower() + "'"
                        first_major = False
                    else:
                        filter += " or major eq " + "'" + major.lower() + "'"
                filter += ")"
            if instructor:
                use_full_search_mode = True
                has_vector = False
                query_text = instructor
            else:
                query_text = query_text.get("search_query")
        
        # normalize week days and do/not
        original_user_query = original_user_query.replace("monday", "Monday")
        original_user_query = original_user_query.replace("tuesday", "Tuesday")
        original_user_query = original_user_query.replace("wednesday", "Wednesday")
        original_user_query = original_user_query.replace("thursday", "Thursday")
        original_user_query = original_user_query.replace("friday", "Friday")
        original_user_query = original_user_query.replace("do", "DO")
        original_user_query = original_user_query.replace("not", "NOT")

        # STEP 2: Retrieve relevant documents from the search index with the GPT optimized query

        # If retrieval mode includes vectors, compute an embedding for the query
        vectors: list[VectorQuery] = []
        if has_vector:
            vectors.append(await self.compute_text_embedding(query_text))

        # Only keep the text query if the retrieval mode uses text, otherwise drop it
        if not has_text:
            query_text = None

        results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions, use_full_search_mode)

        sources_content = self.get_sources_content(results, use_semantic_captions, use_image_citation=False)
        content = "\n".join(sources_content)

        # STEP 3: Generate a contextual and content specific answer using the search results and chat history

        # Allow client to replace the entire prompt, or to inject into the exiting prompt using >>>
        system_message = self.get_system_prompt(
            overrides.get("prompt_template"),
            self.follow_up_questions_prompt_content if overrides.get("suggest_followup_questions") else "",
        )

        response_token_limit = 1024
        messages_token_limit = self.chatgpt_token_limit - response_token_limit
        messages = self.get_messages_from_history(
            system_prompt=system_message,
            model_id=self.chatgpt_model,
            history=history,
            # Model does not handle lengthy system messages well. Moving sources to latest user conversation to solve follow up questions prompt.
            user_content=original_user_query + "\n\nSources:\n" + content,
            max_tokens=messages_token_limit,
        )

        data_points = {"text": sources_content}

        extra_info = {
            "data_points": data_points,
            "thoughts": [
                ThoughtStep(
                    "Original user query",
                    original_user_query,
                ),
                ThoughtStep(
                    "Generated search query",
                    query_text,
                    {"use_semantic_captions": use_semantic_captions, "has_vector": has_vector},
                ),
                ThoughtStep("Results", [result.serialize_for_results() for result in results]),
                ThoughtStep("Prompt", [str(message) for message in messages]),
            ],
        }

        chat_coroutine = self.openai_client.chat.completions.create(
            # Azure Open AI takes the deployment name as the model name
            model=self.chatgpt_deployment if self.chatgpt_deployment else self.chatgpt_model,
            messages=messages,
            temperature=overrides.get("temperature") or 0.7,
            max_tokens=response_token_limit,
            n=1,
            stream=should_stream,
        )
        return (extra_info, chat_coroutine)