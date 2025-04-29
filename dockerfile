FROM python:3.11
WORKDIR /home/sigeo/do_search

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD [ "python", "pesquisa_do.py" ]