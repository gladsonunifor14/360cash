"""Textos padrão criados para cada escritório: termos LGPD/confidencialidade/uso e contrato de adesão.

São modelos iniciais; o escritório deve revisá-los com seu jurídico e publicar novas versões.
"""

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContractTemplate, Office, Term, TermAcceptance, User

TERMS = {
    "uso": (
        "Termos de Uso da Plataforma 360cash",
        """# Termos de Uso

1. **Objeto.** A plataforma 360cash é disponibilizada pelo escritório de contabilidade ("ESCRITÓRIO") a seus
clientes e colaboradores para execução de serviços de BPO Financeiro, consultoria contábil e tributária.
2. **Acesso.** O acesso é pessoal e intransferível, protegido por senha e código de verificação (OTP) enviado
por e-mail. O usuário é responsável pela guarda de suas credenciais e deve comunicar imediatamente qualquer
uso não autorizado.
3. **Informações enviadas.** O usuário declara que os documentos, notas fiscais e extratos enviados são
verídicos e que possui autorização para compartilhá-los.
4. **Registros.** Todas as operações são registradas em trilha de auditoria (usuário, data/hora, IP e
alterações realizadas), que poderá ser utilizada como prova das ações executadas.
5. **Disponibilidade.** A plataforma é fornecida com esforços razoáveis de disponibilidade e segurança.
6. **Foro.** Fica eleito o foro da sede do ESCRITÓRIO.""",
    ),
    "privacidade": (
        "Política de Privacidade e Tratamento de Dados Pessoais (LGPD)",
        """# Política de Privacidade (Lei nº 13.709/2018 – LGPD)

1. **Controlador e operador.** A empresa cliente é controladora dos dados pessoais contidos em seus
documentos financeiros; o ESCRITÓRIO atua como operador, tratando-os exclusivamente para a prestação dos
serviços contratados (art. 39 da LGPD). Para os dados dos usuários da plataforma, o ESCRITÓRIO é controlador.
2. **Dados tratados.** Dados cadastrais (nome, e-mail, CPF/CNPJ), dados de acesso (IP, data/hora, dispositivo),
documentos fiscais (NF-e), extratos bancários e de aplicações, contratos e procurações.
3. **Finalidades e bases legais.** Execução de contrato (art. 7º, V), cumprimento de obrigação legal ou
regulatória (art. 7º, II), exercício regular de direitos (art. 7º, VI) e legítimo interesse para segurança e
prevenção a fraudes (art. 7º, IX).
4. **Compartilhamento.** Apenas com suboperadores necessários (hospedagem, envio de e-mails, agregador de
Open Finance mediante consentimento do titular no banco, provedor de IA para classificação de lançamentos
sem dados identificadores) e autoridades quando exigido por lei.
5. **Segurança.** Criptografia em trânsito (TLS), senhas com hash Argon2, autenticação em dois fatores,
segregação de dados por escritório e cliente, trilha de auditoria e princípio do menor privilégio.
6. **Retenção.** Documentos fiscais e contábeis são mantidos pelos prazos legais (no mínimo 5 anos, art. 173
do CTN); demais dados, enquanto durar a relação contratual.
7. **Direitos do titular.** Confirmação, acesso, correção, anonimização, portabilidade, eliminação, informação
sobre compartilhamento e revogação do consentimento (art. 18), mediante solicitação ao Encarregado (DPO)
pelo e-mail contato@360cash.tech.
8. **Incidentes.** Incidentes de segurança relevantes serão comunicados à ANPD e aos titulares (art. 48).""",
    ),
    "confidencialidade": (
        "Termo de Confidencialidade e Sigilo Profissional",
        """# Termo de Confidencialidade

1. As partes obrigam-se a manter sigilo sobre todas as informações financeiras, fiscais, contábeis,
bancárias, comerciais e pessoais a que tiverem acesso em razão dos serviços ("Informações Confidenciais").
2. O ESCRITÓRIO observará o sigilo profissional previsto no Código de Ética Profissional do Contador
(NBC PG 01) e o sigilo bancário das informações recebidas (LC nº 105/2001).
3. As Informações Confidenciais somente serão utilizadas para a prestação dos serviços, sendo vedada sua
divulgação a terceiros sem autorização expressa, salvo determinação legal ou judicial.
4. A obrigação de sigilo permanece por 5 (cinco) anos após o término da relação contratual.
5. O descumprimento sujeitará a parte infratora à reparação das perdas e danos comprovados.""",
    ),
}

CONTRACT_TITLE = "Contrato de Prestação de Serviços de BPO Financeiro (Adesão)"
CONTRACT_BODY = """# Contrato de Prestação de Serviços de BPO Financeiro

**CONTRATADA:** {{escritorio_razao_social}}, inscrita no CNPJ sob o nº {{escritorio_cnpj}}.
**CONTRATANTE:** {{cliente_razao_social}}, inscrita no CNPJ sob o nº {{cliente_cnpj}}.

Este é um contrato de adesão (art. 54 do Código de Defesa do Consumidor e arts. 423 e 424 do Código Civil).
As cláusulas foram estabelecidas pela CONTRATADA e aceitas eletronicamente pela CONTRATANTE.

## 1. Objeto
Prestação de serviços de BPO (terceirização de processos) Financeiro, compreendendo: (a) importação e
classificação gerencial de notas fiscais emitidas e recebidas; (b) conciliação e classificação de extratos
bancários e de aplicações financeiras; (c) elaboração de Fluxo de Caixa, DRE gerencial e relatórios gerenciais
em painéis de BI; (d) consultoria contábil e tributária vinculada às informações processadas.

## 2. Obrigações da CONTRATANTE
Enviar tempestivamente os documentos (XML de NF-e, extratos, contratos), classificar inicialmente os
lançamentos bancários conforme o histórico quando solicitado e manter seus dados cadastrais atualizados.
A CONTRATANTE é responsável pela veracidade e integridade das informações enviadas.

## 3. Obrigações da CONTRATADA
Executar os serviços com zelo e técnica, observar as Normas Brasileiras de Contabilidade, manter sigilo
profissional e proteger os dados nos termos da LGPD e do Termo de Confidencialidade.

## 4. Remuneração
Honorários mensais de **R$ {{mensalidade}}**, com vencimento no dia 10 de cada mês, reajustados anualmente
pelo IPCA/IBGE.

## 5. Vigência e rescisão
Vigência a partir de {{data_inicio}}, por prazo indeterminado, podendo ser rescindido por qualquer das partes
mediante aviso prévio de 30 (trinta) dias, sem multa.

## 6. Limitação de responsabilidade
Os relatórios gerenciais são elaborados com base nas informações fornecidas pela CONTRATANTE e não substituem
a escrituração contábil oficial.

## 7. Proteção de dados
As partes observarão a Lei nº 13.709/2018 (LGPD), atuando a CONTRATADA como operadora dos dados pessoais
tratados por conta da CONTRATANTE.

## 8. Aceite eletrônico
O aceite eletrônico, registrado com data, hora, IP, usuário e hash (SHA-256) deste documento, tem validade
jurídica nos termos da MP nº 2.200-2/2001, art. 10, § 2º.
"""


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def seed_office_defaults(db: Session, office: Office) -> None:
    for kind, (title, body) in TERMS.items():
        db.add(Term(office_id=office.id, kind=kind, version=1, title=title, body=body, content_sha256=sha256(body)))
    db.add(ContractTemplate(office_id=office.id, version=1, title=CONTRACT_TITLE, body=CONTRACT_BODY))


def current_terms(db: Session, office_id: str) -> list[Term]:
    terms = db.scalars(
        select(Term).where(Term.office_id == office_id, Term.is_active).order_by(Term.kind, Term.version.desc())
    )
    latest: dict[str, Term] = {}
    for t in terms:
        latest.setdefault(t.kind, t)
    return list(latest.values())


def pending_terms(db: Session, user: User) -> list[Term]:
    accepted = set(db.scalars(select(TermAcceptance.term_id).where(TermAcceptance.user_id == user.id)))
    return [t for t in current_terms(db, user.office_id) if t.id not in accepted]


def accept_current_terms(db: Session, user: User, ip: str | None, user_agent: str | None) -> list[TermAcceptance]:
    out = []
    for term in pending_terms(db, user):
        acc = TermAcceptance(term_id=term.id, user_id=user.id, content_sha256=term.content_sha256, ip=ip,
                             user_agent=(user_agent or "")[:300])
        db.add(acc)
        out.append(acc)
    return out
