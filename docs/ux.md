# Diretrizes de UX aplicadas

Objetivo: menos carga cognitiva, clareza operacional e automação transparente para operadores de BPO
Financeiro, que repetem tarefas com dados sensíveis e sob pressão por precisão.

## 1. Torre de controle (`/`)

| Diretriz | Como ficou |
|---|---|
| Cada dado leva a uma ação | Os indicadores são botões que abrem a tela já filtrada (ex.: “4 títulos atrasados” → `/financeiro?urgency=atrasado`). Cada item da fila de trabalho tem “Resolver →” com rota e empresa. |
| Status por criticidade | Atrasado (vermelho, triângulo), Para hoje (âmbar tracejado, relógio), Concluído (verde, check) e Atenção. Fila ordenada por criticidade. API: `GET /v1/control-tower`. |
| Multiempresa | A tabela “Empresas” consolida todas as carteiras; “Abrir empresa” troca o contexto e vai direto ao financeiro. |
| Integrações | Painel com o status de cada conta bancária (Conectado, Reautenticar, Falha, Importação manual), última sincronização e motivo do erro. |

## 2. Troca de contexto e busca global (cabeçalho fixo)

- **Empresa em atendimento** no cabeçalho, com *chips* das últimas empresas e atalhos **Alt+1…5**. Trocar de
  empresa mantém a tela e os filtros atuais; a escolha é lembrada durante a sessão.
- **Busca global** (`/` ou Ctrl+K): uma só barra entende CNPJ/CPF (com ou sem máscara), nome de cliente ou
  fornecedor, valor (`1.234,56`) ou nº de nota/documento. Procura em todas as empresas, navegável por ↑/↓ e
  Enter, e abre o resultado já na empresa certa. API: `GET /v1/search?q=`.

## 3. Contas a pagar e receber (`/financeiro`)

| Diretriz | Como ficou |
|---|---|
| Tela dividida | O título abre com o documento (PDF, imagem ou XML da NF-e) à esquerda e os campos à direita, sem trocar de aba. Títulos gerados de NF-e já vêm com o XML anexado. |
| Aprovação em lote | Seleção múltipla mostra a quantidade e o saldo; Aprovar, Agendar, Liquidar e Cancelar abrem uma confirmação com o total a pagar, o total a receber e o total do lote, além dos títulos que ficarão de fora e o motivo. A API exige `expected_total` igual ao total exibido: se algo mudou entre a pré-visualização e o clique, a operação é recusada. |
| Histórico | Mini-feed em cada título, montado da trilha de auditoria: “Fulano criou o título”, “alterou Valor de R$ 100,00 para R$ 120,00”, “mudou a situação de aberto para aprovado”, “anexou um documento”. |
| Geração automática | NF-e recebida gera conta a pagar e emitida gera conta a receber, uma por duplicata (`cobr/dup`), com a conta gerencial vinda do CFOP. Cancelamento da NF-e cancela os títulos em aberto. |

## 4. Conciliação bancária (`/conciliacao`)

| Diretriz | Como ficou |
|---|---|
| Match inteligente | Cartões lado a lado (lançamento do extrato ⇄ título sugerido) com o percentual de confiança. Basta “Confirmar”. O motor pondera valor, proximidade da data, nome do favorecido e nº do documento no histórico. Lançamentos fora da janela de datas (5 dias antes da emissão até 60 dias após o vencimento) não são sugeridos; diferenças acima de 10% só são sugeridas com evidência no histórico. |
| Divergências | Quando os valores não batem, a tela já mostra a diferença e oferece **Criar juros/multa**, **Desconto** ou **Lançamento parcial**, com a explicação do que cada um faz. O lançamento é rateado (principal + juros/desconto em contas próprias) e o DRE e o fluxo de caixa usam esse rateio. Toda conciliação pode ser desfeita. |
| Status da integração | Faixa no topo com o status de cada banco; falha de token/consentimento no Open Finance marca a conta como “Reautenticar” e aparece também na torre de controle. |
| Conciliação manual | Para lançamentos sem sugestão: escolhe-se o lançamento e o título, e as mesmas ações aparecem conforme a diferença. |

## 5. Acessibilidade e usabilidade

- **Cor nunca sozinha**: todo status combina cor, ícone de forma distinta e texto (`StatusTag`). O “para hoje” também
  muda o estilo da borda (tracejada).
- **Teclado de ponta a ponta**:
  - Listas: ↑/↓/Home/End navegam, Espaço seleciona e Enter abre.
  - Conciliação: Enter confirma, J/D/P escolhem juros, desconto ou parcial.
  - Formulários: seguem a ordem do Tab e Enter salva; Esc volta.
  - Diálogos: são modais nativos com foco no botão de confirmar, que só é habilitado depois de exibir o total.
  - Navegação: link “pular para o conteúdo” e foco movido para o título a cada troca de tela.
- **Erros acionáveis**: a API traduz toda validação para português citando o campo, por exemplo
  “O campo 'Data de vencimento' não pode ser anterior à 'Data de emissão'”. A resposta traz `erros[].loc`, e a tela
  marca o campo (`aria-invalid`), mostra a mensagem abaixo dele e leva o foco até ele. Regras de negócio seguem o
  mesmo formato (“O valor do extrato (R$ 702,19) difere do saldo do título (R$ 689,40) em R$ 12,79. Use
  ‘Juros/multa’…”).
- Contraste de foco visível (`:focus-visible`) e suporte a tema escuro.
