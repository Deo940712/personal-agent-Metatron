# Metatron  �X �ӤH��{ + ���Ѯw�U�z

> �c�餤�� | [English](README-en.md)

�@��**�L���A**���ӤH AI �U�z:�޲z��{�P�ݿ�B����業�x(Threads / X / FB)�s��
�K���z�i Obsidian ���Ѯw�B�l�� vibe coding �M�׶i�סC�X���� Discord �ƨƱ��B
���������;�b�a�� CLI �P Obsidian�C

**�֤߭���:�֤ߤ��ֿn��ܪ��A�C** Discord/OpenCode �� UI �i�H������ session�A
���C�h�T�����O�W�� run�GŪ�v�¸�� �� ���� �� �g���Ҽg�^ �� ����C�s��ʤ��a
�۰ʭ�����q��ѡA�Ӿa DB1/Beacon/vault/transcript �����c�ƪ��A�P�����˯��C

## �[�c�`��

```
�ϥΪ�(CLI / Discord / ����O / MCP)
        �x
        ��
�z�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�{
�x Orchestrator(�L���A,�@���I�s�Y����)�x
�x Ū���A �� ���u�l agent �� ��X �� �g�^ �x
�|�w�w�w�w�w�w�s�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�s�w�w�w�w�w�w�w�}
       �x scoped ���          �x ���c�ƴ���
       ��                     ��
   �l agents �w�w���עw�w? writer.py(�ߤ@�g�J�f:���ҫḨ�a)
       �x                     �x
       ��                     ��
�z�w�w�w�w�w�w�w�w�w�w�w�w�w�w�{   �z�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�w�{
�x DB1 state.db  �x   �x DB2 Obsidian vault     �x
�x SQLite        �x   �x Markdown ���Ѯw         �x
�x System of     �x   �x semantic/ episodic/    �x
�x Record(7 ��) �x   �x agent/(�� agent ������)�x
�|�w�w�w�w�w�w�s�w�w�w�w�w�w�w�w�}   �|�w�w�w�w�w�w�w�w�w�w���w�w�w�w�w�w�w�w�w�w�w�w�}
       �x  �]���]�H(���d�ȥN��)  �x
       �|�w�w�w�w�w�w�w�w�w�w�s�w�w�w�w�w�w�w�w�w�w�w�w�}
                  ��
   �N�x�s transcript(���ä��R,�i�^��)
   �V�q���� index.db(�l�ͪ�,�i���ɭ���)
```

�|���x�s�h,�U�q��¾:

| �x�s | ���� |
|---|---|
| **DB1** `state.db`(SQLite) | System of Record:��{�B�ݿ�B�M�סB�ƥ�B��СB�ݽT�{���� |
| **DB2** Obsidian vault(Markdown) | �H�����Ѥ���:�A�b Obsidian Ū�g�����O |
| **�N�x�s** transcript(JSONL + ����) | ��l�O���h:�]�H�e�����,append-only �ä��R |
| **�V�q����** index.db(sqlite-vec + FTS5) | �l�ͪ�:�a�F�R������,���s�ߤ@��� |

## �O�Шt��(�֤߽��I)

�O�Ы��ʽ���|�h�B���ͩR�g���Ρu���d�ȥN�¡v�޲z(��Ų memory-river / MemGPT /
Mem0 / Hermes ��,�]�p�̾ڨ� [ARCHITECTURE.md](ARCHITECTURE.md) ��12):

| �h | �^�������D | �s�� |
|---|---|---|
| Working State | �u������F?�v | DB1(tasks / cursors / projects) |
| Episodic ���` | �u�o�͹L����?�v | DB1 events �� �]�H�i vault `episodic/` |
| Semantic �y�q | �u�ڪ��D����?�v | vault `semantic/`(�K�媾��)+ `agent/`(�� agent �����n/�аV/SOP) |
| Procedural �{�� | �u���?�v | `agents/*.md` ���� + `skills/` �{���X |

**���d�ȥN��**:�O�гQ�˯��R���N�^��B�[���δN�I��;�k�s�i�U����(�O�d 14 ��,
�����Q�ޥΥi�_��)�� ����� LLM �]�H�� vault ���O�C**��� = ���A�D�ʸ��J,
������R��**�X�X���æb�N�x�s,�]�H���O�a `source_ids` �H�ɥi�u�^��vŪ�^���C

**�|�q���p�˯�**:
```
? index-first(INDEX �@��y�z,�s����)
? FTS5 ����(���� trigram,�s embedding ����)
? �V�q KNN(sqlite-vec,�y�N�˯�)
? rehydrate(�u source_ids Ū�^���,�n�T���Ʀr/�W�r��)
```

�޳N�Ӹ`(���� API�B���ܶq�B�G�٫�_):[docs/MEMORY-zh.md](docs/MEMORY-zh.md)

### �h�h�O�СG�ثe���b����

���n�V�c�u�x�s���h�v�u�˯����q�v�u�� run ��� checkpoint�v�P�uLLM �ۥD
STM��MTM��LPM paging�v�C�ثe�u�� **A�G�L���A���� + �����˯�**�w��@�F
**B�GTask Capsule**�B**C�Gtask-scoped warm set**�B**D�GLLM �ۥD paging**���O
�Կ��סA�� A��B��C��D �H�u�����Ȥ���A�e�@�Ũ����N���W�[�����סC

**�O�бj��(part-004.5,�w����,�� 2026 �פ����)**:�D�D�s��ʻ]�H(Membox:
�P�D�D������V related ��s)�B�٬ް��� + supersede ����(Mneme:�s�°��n����
�O�d�Brecall Ū��Q���N���O�|���ܷs��)�BRRF ��q�ĦX�˯�(Cognis:k=60,
�j�R���O�d�s�����u��)�C�ݭq(Ĳ�o�����):cross-encoder rerank(golden
queries �X�ƦW���D��)�Bper-category �I��t�v(�u��ϥ� 1-2 �릳�ƾڮ�)�C

## �Ҧ� Agent ��¾��

**�M�ץN��:Metatron**(�ѬɮѰO�x)�X�Xorchestrator ���H�C�l agent �q
Metatron ���U�ѨϦW�D��(��ܼh�R�W;�{���X�ѧO�ź����޳N�W�H�O API í�w,
����M�g�� [AGENTS.md](AGENTS.md) ��Angel naming registry)�C

**�ݼ�:Orchestrator + �L���A�l agent**(2026 �~ LangGraph / Claude Agent SDK /
OpenAI Agents SDK ���Ī��Ͳ��з�)�C�l agent �� scoped ��J�B�^���c�ƴ��סB�Y��C

### �g�J�K�ߡGAgent �i�� scoped tools�A�{�����ҡA��@ commit boundary

�l agent �i�� allowlist �ۥD�I�s read/propose/�C���I auto-apply capability�A���ݭn
Metatron �N��C�� tool call�F�� LLM �ä����o raw SQL�BDB connection�B��N�ɮ׼g�J
�λr `writer.apply`�Cagent/�ϥΪ̵o�_�� proposal mutation �� `writer.apply` ���ҡF
���H������� job pipeline�]�p�]���]�H�^���U�۪� deterministic validated write path�F
��̬Ҥ�¶�L���ҡC�����I�ާ@ preview��confirm�A�O�ɤ@�ߩڵ��CMetatron �O control
plane�A���O�Ҧ��u�㪺�P�B data-plane proxy�C

### �l agent �@��

| �Ѩ� / �l Agent | ¾�� | ��J | ��X | ���A |
|---|---|---|---|---|
| **Sandalphon** �X `schedule` | �۵M�y�� �� ��{/�ݿ촣��(�u���ѤU�Ȩ��I�}�|���e30������v);rrule ���Ʀ�{ | �ϥΪ̭�y + �{����{ | `schedule_change` / `task_change` ���� | ? |
| **Raziel** �X `consolidator` | �]���]�H:����ƥ� �� ��x�K�n(episodic)/ �ϥΪ̰��n(agent/profile);�C�ӨM���L��������,���o��c�ӷ� | ��� events �妸 | �]�H��(kind/title/summary/tags/source_ids/confidence) | ? |
| **Jophiel** �X `curator` | �K�����(0-10 �h�� 4.0)�B�����B�̤���h���B�J vault;manual_tags �ä��л\ | inbox ���O�妸 | `classify_note` ���� | ? |
| **Zerachiel** �X `recall` | ���Ѯw�ݵ�:index��FTS���V�q RRF �ĦX + rehydrate;�D�Ťޥγv�@���үu���(���ޥξ㵪���);superseded_by ����;�Y�� found/not_found(found ���� ?1 ���ҹL�ޥ�,�ŤޥΤ@�� not_found,part-006 �w��@) | �d�ߦr�� | �a�ޥΪ����� | ? |
| **Uriel** �X `coding_tracker` | vibe coding �i��:�T����Ū���y(git + `.beacon/CURRENT` + OpenCode sessions,beacon �̰��v��)�� �C�M�� phase/blockers/next | �w���U�M�� | `project_update` ���� | ? |
| **Cassiel** �X `advisor` | �D�ʫ�ĳ:world-diff quiet-tick(�L�ܤƹs LLM)�� ���i�L�� advice(�|�����h��);action ���T�{�B�շǦ^�X�� facet | world-diff + ���n facets | `advice` ���� + Discord ���� | ? part-009 |
| **scout** �X `Knowledge Scout` | �����Ѱ���:allowlist fail-closed ���(**�D LLM**)+ external_untrusted �j��;�uĲ�o����U��s | watchlist ��� / goal �ʤf | inbox ���O(�a���� + �ìV����) | ? part-008 |
| **Anael** �X `librarian` | vault �ϮѺ޲z��:�t��/�_��/����/tag �������@;�ⶥ�q�B�ַӥi�^�u�B�ä��R�� | vault.scan �T�w�ʳ��i | `vault_maintenance` ����(dry-run ����) | ?? backlog-017 |
| sync-{threads,x,fb} | ���x����޽u(**�D LLM**,�� CLI,idempotent �i���) | cursor | new_count, status | threads ? / x,fb ?? phase-0 probe ���� |

> Michael / Camael / Raphael / Ophanim / Azrael �O�ϥΪ̴��W��**�ثe�L���� agent** ���ѨϦW,
> �w�b [AGENTS.md](AGENTS.md) ��Angel naming registry �uArchived�v�q�ʦs�C���Y�u���W�ߦ� agent �~�ҥ�,���w������C

�l agent ���⫬:**�¨�ƫ�**(�榸 LLM �I�s�B�L�u��B�i������աX�Xschedule/
consolidator/curator/librarian/coding_tracker)�P**�N�z��**(�ثe recall �ϥέ��N��Ū
�u��)�C���ӬO�_����h agent �u��A�̡u�U�@�B�O�_�u���̿�e�@�B���G�v�M�w�A�è�
scope/budget/timeout ����Fshared-state commit ���u�� deterministic writer boundary�C

## ����

| ���� | ���� | Ū/�g | ���A |
|---|---|---|---|
| **CLI** | �}�o�B�Ƶ{ job | Ū+�g | ? |
| **Obsidian** | ���Ѯw�\Ū/�s��(vault �N�O UI) | Ū+�g | ?(�s����) |
| **Discord bot** | �X��:�ƨƱ�(�w����?���s�����a)+ ���� DM ����;�p�H server �� user id | Ū+�g(�� writer+�T�{) | ? �{���� |
| �������O | �b�a�`�� + �t�ΰ��d(127.0.0.1:7777;GET-only + mode=ro �T�h��Ū) | ��Ū | ? |
| MCP server(stdio + Tailscale HTTP) | �b OpenCode/Claude Code ���ݧU�z/�Ƶ{/���ݶ}�o�j�� | Ū+�g(�g�� pending �T�{) | ? �{����(VPS �u�� QA �����) |

���� = �� adapter,�s�~���޿�Ftoday/week/proj/todo/done/recall �w�@�� typed
`core/tools/` ��O�h�C�\���agent��interface��permission��storage �v�¯x�}��
[docs/TOOLS.md](docs/TOOLS.md)�A�����]�p�� [INTERFACES.md](INTERFACES.md)�C

## �ϥ�

```bash
# ��l��(idempotent)
python -m core.stm init

# ��{/�ݿ�/�M�� CRUD
python -m core.stm schedule add "�}�|" --start 2026-07-15T14:00 --remind 2026-07-15T13:30
python -m core.stm schedule list
python -m core.stm tasks add "�R�߬�" --due 2026-07-16T20:00
python -m core.stm projects set my-agent --phase "part-004" --next "curator"

# �۵M�y��(�� LLM key)
python -m core.agent "���ѤU�Ȩ��I������}�| ���e30������"   # �w�� �� y �� ���a

# �Ƶ{ job(Windows Task Scheduler / cron)
python -m core.agent --job remind        # �������(+ �����O�ɫݽT�{)
python -m core.agent --job consolidate   # �]���]�H

# Discord bot(�� token,���U)
python -m channels.discord_bot
```

### ����ܼ�

| �ܼ� | �γ~ |
|---|---|
| `MY_AGENT_LLM_API_KEY` | LLM(OpenAI �ۮe:OpenAI / OpenRouter / Groq / Ollama) |
| `MY_AGENT_LLM_BASE_URL` | ��t:�D OpenAI �x����I |
| `MY_AGENT_EMBED_BASE_URL` | ��t:embedding �W�ߺ��I |
| `MY_AGENT_DISCORD_TOKEN` | Discord bot token |
| `MY_AGENT_DISCORD_ALLOWED_USER_ID` | Discord �զW��(�r�����j;�� = ����) |

��|�����b `config.py`(`DATA_DIR` ��)�X�X������/�E VPS �u��o���ɮסC

## �i�a�ʳ]�p

| ���I | ���� |
|---|---|
| �O�Ф�ı | �����w�W�h:�C���O���a�ӷ�;recall ���Ѫ��D�Ťޥγv�@���үu��(���ޥξ㵪���);found ���� ?1 ���ҹL�ޥ�,�ŤޥΤ@�� not_found(�{���w�W�h,���H LLM �۳�);�i�^��Ū��� |
| LLM �M���ìV | �C�ӻ]�H�M���L��������(���o��c source_ids);���X����L�ðO log |
| �l agent �üg | ���ר� + ��@ writer + �M�I�h��;�T�{�O�� fail-closed |
| ��ƿ� | ��� append-only �ä��R;�]�H���Ѩƥ�d�b�U����U������;���ޥi���� |
| �R�q�a�� | `agent_runs` �O���C������ status;���h���u�O�� run ���d running |

## �}�o

```bash
python -m pytest tests/ -q     # 852 tests
```

�u�@�y:[Beacon](.beacon/PLAN.md)(plan �� design �� slice �� execute �� verify ��
**adversarial audit** �� archive)�C�C�� slice �k�ɫ�]���ҽ]��(���w�}���u����
�i�ø�|),�o�{���O���b [KNOWN_ISSUES.md](KNOWN_ISSUES.md) ���� regression test�C

| ��� | ���e |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | �t�γ]�p�v��(schema�B�y�{�ϡB�]�p�̾�) |
| [INTERFACES.md](INTERFACES.md) | �����h�]�p(CLI/Discord/����O/MCP) |
| [docs/TOOLS.md](docs/TOOLS.md) | ��O�u��Bagent�B�����B�v���P�x�s�t��x�} |
| [docs/MEMORY-zh.md](docs/MEMORY-zh.md) | �O�Шt�ι�@�W��(API�B���ܶq�B�G�٫�_) |
| [KNOWN_ISSUES.md](KNOWN_ISSUES.md) | �]�ֵo�{�P�״_�O�� |

## �i��

- ? part-001 ��¦�h(schema + CRUD CLI)
- ? part-002 Orchestrator + writer + schedule agent + remind
- ? part-002.5 Discord bot(�ⶥ�q�T�{ + DM ����)
- ? part-003 �O�Ю֤�(�N�x�s/�N��/�]�H/�˯�)
- ? part-003.1 �O�Ь[�c���y����(MEM-01..17 + A/B/C/D ����ج[)
- ? part-003.2 Task Capsule A/B ����(�j���쫬;�P�w retain_a,���勵�� schema)
- ? part-003.5 ��Ū����O(stdlib http.server;127.0.0.1:7777;�T�h��Ū)
- ? part-004 sync skills(threads runner + curator + recall)
- ? part-004.5 �O�бj��(�D�D trace / supersede / RRF �ĦX)
- ? part-005 coding_tracker(git + beacon + opencode �T��,�u�T�� gate �q�L)
- ? part-006 MCP server(��O�u���y/���ʵw��/stdio/Tailscale HTTP)
- ? **part-007 Personal Model**(�Ҿ��X�� profile_facets;pin/forget �w�л\;
  supersede �����O�d;��v vault + recall �i��)
- ? **part-009 Proactive Advisor**(world-diff quiet-tick �s LLM;�|�����h��;
  action ���T�{;�շǦ^�X�� facet)
- ? **part-008 Knowledge Scout**(allowlist fail-closed;external_untrusted �j��;
  ����s�g�J;`--job scout` Ĳ�o��s)
- ?? x/fb-sync phase-0 probe ����(playwright GraphQL �d�I + transform/store + tests)
- ✅ part-010 Scenario Rehearsal(vendored crowd-scenario;bucket firewall;subprocess 隔離;個人 templates;硬標 non_authoritative)
- ✅ part-011 收尾接線(作息 completed 事件 → routine facet → advisor 偏離;advisor 校準降頻;world-diff new_knowledge 訊號;golden queries 回歸)
- ?? �ݨϥΪ����:�u����� / �|��u QA(LLM key / Discord token / threads
  session)+ part-006 VPS + Tailscale �u�� QA(backlog-008)

**852 tests 綠。自適應助理層(§15)四塊完成:Personal Model + Advisor + Scout + Scenario Rehearsal；跨 part 迴圈已接線閉環。**

�e���M��:[threads-sync](https://github.com/Deo940712/threads-sync)(Threads
�w�s�K�� �� Obsidian,�w vendored ���Ĥ@�� sync skill)�C
