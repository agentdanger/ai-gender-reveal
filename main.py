from google.cloud import storage
from google.api_core.client_options import ClientOptions # type: ignore
from google.cloud import documentai
from google.cloud import secretmanager

from fastapi import FastAPI
from fastapi.responses import Response

from starlette.middleware.cors import CORSMiddleware

from openai import OpenAI

# import creds from secretsmanager
project_id = 'personal-website-35'
open_ai_secret = 'open-ai-gender-reveal-key'
location = 'us'
documentai_processor_id = 'gender-reveal-document-processor-id'

secret_client = secretmanager.SecretManagerServiceClient()

open_ai_secret = secret_client.access_secret_version(name=f'projects/{project_id}/secrets/{open_ai_secret}/versions/latest').payload.data.decode('UTF-8')
documentai_processor_id = secret_client.access_secret_version(name=f'projects/{project_id}/secrets/{documentai_processor_id}/versions/latest').payload.data.decode('UTF-8')

def layout_to_text(layout: documentai.Document.Page.Layout, text: str) -> str:
    """
    Document AI identifies text in different parts of the document by their
    offsets in the entirety of the document"s text. This function converts
    offsets to a string.
    """
    # If a text segment spans several lines, it will
    # be stored in different text segments.
    return "".join(
        text[int(segment.start_index) : int(segment.end_index)]
        for segment in layout.text_anchor.text_segments
    )

# start documentai function
def quickstart(file_path: str,
               project_id = project_id,
               location = location,
               processor_id = documentai_processor_id):
    # You must set the `api_endpoint`if you use a location other than "us".
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")

    client = documentai.DocumentProcessorServiceClient(client_options=opts)

    # The full resource name of the processor, e.g.:
    name = client.processor_path(project_id, location, processor_id)

    # Get a processor 
    processor = client.get_processor(name=name)

    # read file from Google Cloud Storage
    gcs = storage.Client()
    bucket = gcs.get_bucket("gender-reveal-documents")
    blob = bucket.blob(file_path)

    image_content = blob.download_as_bytes()

    # Load binary data
    raw_document = documentai.RawDocument(
        content=image_content,
        mime_type="application/pdf",  # Refer to https://cloud.google.com/document-ai/docs/file-types for supported file types
    )

    # Configure the process request
    # `processor.name` is the full resource name of the processor, e.g.:
    # `projects/{project_id}/locations/{location}/processors/{processor_id}`
    request = documentai.ProcessRequest(name=processor.name, raw_document=raw_document)

    result = client.process_document(request=request)

    # For a full list of `Document` object attributes, reference this page:
    # https://cloud.google.com/document-ai/docs/reference/rest/v1/Document
    document = result.document
    # [END documentai_quickstart]
    return document

app = FastAPI()

origins = [
    "https://courtneyperigo.com",
    "https://www.courtneyperigo.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET"]
)

@app.get("/gender-reveal")
async def gender_reveal():
    file_path = "gender-reveal.pdf"
    document = quickstart(file_path)

    document_chunks = [
        layout_to_text(page.layout, document.text)
        for page in document.pages
    ]

    context = " "

    for chunk in document_chunks:
        context += chunk

    openai_client = OpenAI(api_key=open_ai_secret)

    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant that reads the results of non-invasive prenatal test from a young couple to help them with their gender reveal party."
        },
        {
            "role": "user",
            "content": f"Hello, we are having a baby and the results of our NIPT test are in. We haven't looked at the results yet, but we want you to tell us the gender of our baby based on the results we can show you. We only want you to tell us the gender based on the results. Can you help us with that?"
        },
        {
            "role": "assistant",
            "content": "Sure, I can help with that. Please include the results of the NIPT test in text format, and I'll help you determine the gender.  I will only say the word 'male' or 'female' as a response. Nothing else."
        },
        {
            "role": "user",
            "content": f"Great, here are the results of our NIPT test: {context}. That's all. Please tell us the gender as a single word either 'male' or 'female' and nothing else."
        }
    ]

    response = openai_client.chat.completions.create(model="gpt-4-turbo-preview", messages=messages)

    answer = response.choices[0].message.content

    return {"gender": answer}
        
    

@app.get("/")
async def root():
    return {"message": "Gender Reveal Service is working."}

