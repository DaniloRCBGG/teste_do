import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO

import PyPDF2
import requests
from dotenv import load_dotenv
from prefect import flow, task
from prefect.blocks.system import Secret
from prefect.variables import Variable

load_dotenv()
sender_email_credentials = Secret.load("danilo-credentials").get()
recipient_email_credentials = Secret.load("sigeo-email-credentials").get()
do_keys_to_search = Variable.get("do_aplication_search_keys")["VALUES"]


# Mapeamento dos meses para abreviações em português
MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}

# Configurações do e-mail
EMAIL_REMETENTE = os.getenv(
    "SENDER_EMAIL_ADDRESS") or sender_email_credentials["EMAIL"]
EMAIL_SENHA = os.getenv(
    "SENDER_EMAIL_PASSWORD") or sender_email_credentials["PASSWORD"]
EMAIL_DESTINATARIO = os.getenv(
    "RECIPIENT_EMAIL_ADDRESS") or recipient_email_credentials["EMAIL"]

KEYS_TO_SEARCH = os.getenv("KEYS_TO_SEARCH") or do_keys_to_search


@task
def gerar_url_diario_oficial():
    """Gera a URL do Diário Oficial de hoje."""
    data_atual = datetime.now()
    ano = data_atual.strftime("%Y")
    mes_numero = data_atual.month
    mes_abrev = MESES_PT[mes_numero]
    dia = data_atual.strftime("%d")
    return f"https://diariooficial.niteroi.rj.gov.br/do/{ano}/{mes_numero:02d}_{mes_abrev}/{dia}.pdf"


@task
def enviar_email(assunto, corpo):
    """Envia um e-mail com o assunto e corpo fornecidos."""
    msg = MIMEMultipart()
    msg["From"] = EMAIL_REMETENTE
    msg["To"] = EMAIL_DESTINATARIO
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_REMETENTE, EMAIL_SENHA)
            server.sendmail(EMAIL_REMETENTE,
                            EMAIL_DESTINATARIO, msg.as_string())
            print("E-mail enviado com sucesso.")
    except Exception as e:
        print(f"Falha ao enviar e-mail: {e}")


@task
def buscar_dados_no_pdf(url, dados):
    """Busca os dados no PDF e retorna uma mensagem formatada."""
    mensagem_final = f"Relatório de Pesquisa no Diário Oficial\nURL: {url}\n\n"
    encontrou_dado = False

    try:
        response = requests.get(url)
        response.raise_for_status()

        with BytesIO(response.content) as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            texto = "".join(
                [page.extract_text() or "" for page in reader.pages]).lower()

            for dado in dados:
                if dado.lower() in texto:
                    mensagem_final += f"O dado '{dado}' foi encontrado no PDF.\n"
                    encontrou_dado = True
                else:
                    mensagem_final += f"O dado '{dado}' NÃO foi encontrado no PDF.\n"

    except requests.exceptions.RequestException:
        print(f"PDF não encontrado em {url}. Nenhuma ação necessária.")
        return None  # PDF não disponível, apenas retorna sem erro
    except Exception as e:
        print(f"Erro ao processar o PDF: {e}")
        return None  # Retorna sem erro, pois não queremos e-mail nesse caso

    return mensagem_final if encontrou_dado else None


@flow(name="pesquisa no diário oficial", log_prints=True)
def pesquisa_do_flow():
    """Função principal que executa a busca e envia o e-mail se necessário."""
    dados_buscados = [key.strip()
                      for key in KEYS_TO_SEARCH.split(",") if key.strip()]
    url_diario = gerar_url_diario_oficial()

    resultado_pesquisa = buscar_dados_no_pdf(url_diario, dados_buscados)

    if resultado_pesquisa:
        enviar_email("Busca por dados no DO retornou resultados",
                     resultado_pesquisa)
        print(resultado_pesquisa)  # Apenas para depuração
    else:
        print("Nenhum dado procurado foi encontrado no diário oficial")


if __name__ == "__main__":
    pesquisa_do_flow()
