import pymupdf


def extract_text_from_pdf(file_path):

    text = ""


    try:

        document = pymupdf.open(
            file_path
        )


        for page in document:

            text += page.get_text()


        document.close()


    except Exception as error:

        print(
            "PDF extraction error:",
            error
        )


    return text