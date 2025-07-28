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
sender_email_credentials = Secret.load("nao-responda-email-credentials").get()
recipient_email_credentials = Secret.load("sigeo-email-credentials").get()
do_keys_to_search = Variable.get("search_keys")["VALUES"]

# Mapeamento dos meses para abreviações em português
MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}

EMAIL_REMETENTE = os.getenv(
    "SENDER_EMAIL_ADDRESS") or sender_email_credentials["EMAIL"]
EMAIL_SENHA = os.getenv(
    "SENDER_EMAIL_PASSWORD") or sender_email_credentials["PASSWORD"]
EMAIL_DESTINATARIO = os.getenv(
    "RECIPIENT_EMAIL_ADDRESS") or recipient_email_credentials["EMAIL"]

# KEYS_TO_SEARCH agora é um dicionário: {nome: email}
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
def enviar_email_geral(assunto, corpo):
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
            server.sendmail(EMAIL_REMETENTE, EMAIL_DESTINATARIO, msg.as_string())
            print("E-mail padrão enviado com sucesso.")
    except Exception as e:
        print(f"Falha ao enviar e-mail geral: {e}")


@task
def enviar_emails_para_funcionarios(texto_pdf, url):
    """Envia e-mails para os funcionários mencionados no D.O."""
    for nome, email in KEYS_TO_SEARCH.items():
        if nome.lower() in texto_pdf:
            corpo = f"{nome}, seu nome foi citado no Diário Oficial de hoje.\n\nVeja aqui: {url}"
            assunto = f"Nome encontrado no Diário Oficial - {datetime.now().strftime('%d/%m/%Y')}"

            msg = MIMEMultipart()
            msg["From"] = EMAIL_REMETENTE
            msg["To"] = email
            msg["Cc"] = EMAIL_DESTINATARIO
            msg["Subject"] = assunto
            msg.attach(MIMEText(corpo, "plain"))

            try:
                with smtplib.SMTP("smtp.gmail.com", 587) as server:
                    server.starttls()
                    server.login(EMAIL_REMETENTE, EMAIL_SENHA)
                    server.sendmail(EMAIL_REMETENTE, [email, EMAIL_DESTINATARIO], msg.as_string())
                    print(f"E-mail enviado para {nome} ({email}) e CC para atendimento.")
            except Exception as e:
                print(f"Falha ao enviar e-mail para {nome}: {e}")


@task
def buscar_dados_no_pdf(url, dados_dict):
    """Busca os dados no PDF e retorna uma mensagem formatada e texto completo."""
    mensagem_final = f"Relatório de Pesquisa no Diário Oficial\nURL: {url}\n\n"
    encontrou_dado = False

    try:
        response = requests.get(url)
        response.raise_for_status()

        with BytesIO(response.content) as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            texto = "".join([page.extract_text() or "" for page in reader.pages]).lower()

            for nome in dados_dict.keys():
                if nome.lower() in texto:
                    mensagem_final += f"O dado '{nome}' foi encontrado no PDF.\n"
                    encontrou_dado = True
                else:
                    mensagem_final += f"O dado '{nome}' NÃO foi encontrado no PDF.\n"

    except requests.exceptions.RequestException:
        print(f"PDF não encontrado em {url}. Nenhuma ação necessária.")
        return None, None
    except Exception as e:
        print(f"Erro ao processar o PDF: {e}")
        return None, None

    return (mensagem_final if encontrou_dado else None), texto


@flow(name="pesquisa no diário oficial", log_prints=True, retries=4, retry_delay_seconds=3600)
def pesquisa_do_flow():
    """Fluxo principal que pesquisa no D.O., envia e-mail geral e notifica funcionários."""

    url_diario = gerar_url_diario_oficial()
    if not url_diario:
        raise ValueError("Falha ao gerar a URL do Diário Oficial.")

    try:
        response = requests.get(url_diario)
        if response.status_code != 200 or not response.content:
            raise ValueError("Diário oficial ainda não disponível.")
    except Exception as e:
        raise ValueError(f"Erro ao acessar o Diário Oficial: {e}")

    resultado_pesquisa, texto_pdf = buscar_dados_no_pdf(url_diario, KEYS_TO_SEARCH)

    if not resultado_pesquisa:
        raise ValueError("Nenhum dado procurado foi encontrado no Diário Oficial.")

    enviar_email_geral("Busca por dados no DO retornou resultados", resultado_pesquisa)
    enviar_emails_para_funcionarios(texto_pdf, url_diario)


if __name__ == "__main__":
    pesquisa_do_flow()
