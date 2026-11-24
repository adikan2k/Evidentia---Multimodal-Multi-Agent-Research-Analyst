# Evaluation report

Built by `python -m evals report` from the JSON files in this folder. Nothing here is typed by hand.

The corpus is a frozen set of openly licensed pages, mostly Wikipedia. Those pages are cleaner than the open web, so these scores are likely higher than real use would give.

## Retrieval

40 questions over 50 pages cut into 2362 passages. Scores are for the top 10 passages, with a 95% interval in brackets.

| Retriever | Recall@10 | MRR@10 | nDCG@10 |
|---|---|---|---|
| bm25 | 0.571 (0.463 to 0.675) | 0.537 (0.408 to 0.657) | 0.455 (0.363 to 0.545) |
| dense | 0.917 (0.850 to 0.967) | 0.740 (0.644 to 0.833) | 0.751 (0.675 to 0.821) |
| hybrid | 0.858 (0.775 to 0.925) | 0.682 (0.571 to 0.794) | 0.673 (0.591 to 0.751) |
| dense_rerank | 0.938 (0.883 to 0.979) | 0.816 (0.725 to 0.900) | 0.804 (0.739 to 0.863) |
| hybrid_rerank | 0.938 (0.883 to 0.979) | 0.817 (0.727 to 0.900) | 0.804 (0.740 to 0.863) |

Difference per question, second minus first:

| Comparison | Recall@10 | MRR@10 | nDCG@10 |
|---|---|---|---|
| dense minus bm25 | +0.346 (+0.250 to +0.454) | +0.204 (+0.083 to +0.324) | +0.296 (+0.225 to +0.376) |
| hybrid minus dense | -0.058 (-0.113 to -0.008) | -0.058 (-0.128 to +0.008) | -0.077 (-0.118 to -0.041) |
| hybrid_rerank minus hybrid | +0.079 (+0.025 to +0.142) | +0.134 (+0.040 to +0.238) | +0.131 (+0.083 to +0.189) |
| hybrid_rerank minus dense | +0.021 (-0.017 to +0.058) | +0.076 (+0.000 to +0.165) | +0.053 (+0.016 to +0.095) |
| hybrid_rerank minus dense_rerank | +0.000 (+0.000 to +0.000) | +0.001 (+0.000 to +0.002) | +0.000 (+0.000 to +0.001) |

Gold: Gold snippets were drafted by Claude from each question's pages and checked word for word against the page text. See evals/questions.jsonl.

## How reliable is the checker?

### Deliberately broken claims

A third of the test pairs were broken on purpose: given the wrong quote, one fact changed, or a detail added. This counts how many each checker refused to pass as supported. No labels are involved.

| Checker model | Wrong quote | Changed fact | Added detail | All broken pairs |
|---|---|---|---|---|
| claude-sonnet-5-5 | 17 of 17 | 16 of 17 | 16 of 16 | 49 of 50 |
| claude-haiku-5-5 | 17 of 17 | 16 of 17 | 15 of 16 | 48 of 50 |
| claude-opus-5-5 | 17 of 17 | 17 of 17 | 16 of 16 | 50 of 50 |

### Agreement with a person

NOT DONE. No person has labelled these pairs, so there is no agreement-with-a-human figure.

### Agreement with a second model (not a person)

Claude Fable 5.2, shown only the claim and the quote. NOT a person. This is one model agreeing with another from the same family. It says the checker is consistent with a stronger model; it does not say either is right. Convention used: a pronoun in the quote that plainly refers to the page's subject is not counted as a missing fact, but an added number, date, cause or 'who said it' is.

| Checker model | Agreement | Cohen's kappa | Real pairs | Built pairs |
|---|---|---|---|---|
| claude-sonnet-5-5 | 0.893 (0.840 to 0.940) | 0.829 (0.744 to 0.903) | 0.910 | 0.860 |
| claude-haiku-5-5 | 0.900 (0.853 to 0.947) | 0.838 (0.753 to 0.913) | 0.910 | 0.880 |
| claude-opus-5-5 | 0.880 (0.827 to 0.927) | 0.809 (0.723 to 0.885) | 0.890 | 0.860 |

## Baselines against pipelines

For each claim, does the evidence the system points to back it? Baseline evidence is the cited passage; pipeline evidence is the quote. Judge: claude-opus-5-5 with the checker's rubric. Shown as backed means: all claims for a baseline; claims labelled supported for a pipeline.

| System | Shown as backed that are fully backed | Shown as backed per question | All claims per question | Characters to read per claim | Cost per question |
|---|---|---|---|---|---|
| Baseline (one-shot RAG), Sonnet writer | 0.917 (0.877 to 0.953) | 7.85 | 7.85 | 1039 | $0.0141 |
| Pipeline, Sonnet writer and checker | 0.928 (0.895 to 0.961) | 5.58 | 7.75 | 195 | $0.0401 |
| Baseline, Haiku writer | 0.921 (0.866 to 0.961) | 7.60 | 7.60 | 1039 | $0.0010 |
| Pipeline, Haiku writer and checker | 0.888 (0.844 to 0.927) | 6.25 | 7.53 | 170 | $0.0030 |
| Pipeline with partial claims tightened (the product default) | 0.925 (0.901 to 0.948) | 7.62 | 7.78 | 188 | $0.0491 |

Fully backed, each system minus the Sonnet baseline, per question:

| System | Difference | Questions |
|---|---|---|
| Pipeline, Sonnet writer and checker | -0.013 (-0.060 to +0.032) | 40 |
| Baseline, Haiku writer | +0.007 (-0.032 to +0.047) | 40 |
| Pipeline, Haiku writer and checker | -0.030 (-0.079 to +0.018) | 40 |
| Pipeline with partial claims tightened (the product default) | +0.009 (-0.032 to +0.055) | 40 |

DeepEval faithfulness (stock metric, same judge model): baseline 1.000 (1.000 to 1.000), pipeline 1.000 (1.000 to 1.000).

## Questions the corpus cannot answer

20 easy general-knowledge questions whose answers are not in the corpus. A good system presents no backed claim, or only claims its evidence really backs. Written by Claude as a stress test; not a sample of real questions.

| System | Stayed quiet | Answered from memory | Claims shown as backed | Of those, fully backed |
|---|---|---|---|---|
| Baseline (one-shot RAG), Sonnet writer | 20 of 20 | 0 of 20 | 0 | 0 |
| Pipeline, Sonnet writer and checker | 20 of 20 | 0 of 20 | 0 | 0 |
| Baseline, Haiku writer | 19 of 20 | 0 of 20 | 2 | 2 |
| Pipeline, Haiku writer and checker | 20 of 20 | 0 of 20 | 0 | 0 |

## Nasty tests

Hand-made cases show behaviour on these cases only. This is evidence, not a security guarantee.

| Case | Passed |
|---|---|
| hidden_instructions | 5 of 5 |
| paywall | 5 of 5 |
| contradiction | 5 of 5 |

## The auditor on LLM-AggreFact

LLM-AggreFact pairs a claim with a document and a person's label: supported or not. The sample is 50 test rows from each of its 11 sub-datasets. Balanced accuracy is computed per sub-dataset, then averaged, with a 95% interval. The auditor finds quotes, checks them by code, then a checker sees only the claim and the quotes; only 'supported' counts as supported. The direct baseline is the same model shown the whole document and asked yes or no. Prompts were fixed on dev rows before this run.

| System | Balanced accuracy | Partial counted as supported | Cost per claim |
|---|---|---|---|
| auditor, haiku | 0.688 (0.646 to 0.728) | 0.696 (0.648 to 0.748) | $0.00045 |
| direct, haiku | 0.768 (0.721 to 0.811) |  | $0.00024 |

haiku, 550 rows: auditor minus direct -0.080 (-0.120 to -0.038). Auditor labels: 199 supported, 189 partial, 141 not_found, 21 contradicted. 415 rows had at least one quote found word for word.

| System | Said supported | Of those, right | Supported rows accepted | Unsupported rows rejected |
|---|---|---|---|---|
| auditor | 199 | 0.915 | 0.523 | 0.916 |
| direct | 279 | 0.910 | 0.730 | 0.876 |

| Sub-dataset | Rows | Auditor | Direct |
|---|---|---|---|
| AggreFact-CNN | 50 | 0.769 | 0.894 |
| AggreFact-XSum | 50 | 0.554 | 0.747 |
| ClaimVerify | 50 | 0.755 | 0.717 |
| ExpertQA | 50 | 0.482 | 0.502 |
| FactCheck-GPT | 50 | 0.625 | 0.625 |
| Lfqa | 50 | 0.871 | 0.903 |
| RAGTruth | 50 | 0.778 | 0.844 |
| Reveal | 50 | 0.792 | 0.851 |
| TofuEval-MediaS | 50 | 0.483 | 0.729 |
| TofuEval-MeetB | 50 | 0.802 | 0.847 |
| Wice | 50 | 0.651 | 0.786 |

## Two judges on LLM-AggreFact

A claim gets a verdict only when the quote judge (exact quotes, then a check on the quotes alone) and the page judge (the claim and the page) agree. Otherwise it is 'needs a human'. Flag precision: of the claims flagged, the share people label unsupported. Supported precision: of the claims called supported, the share people label supported. Coverage: the share that get a verdict. 95% intervals in brackets.

### dev550: quote judge claude-haiku-5-5 with quote context, page judge claude-haiku-5-5 (550 rows)

| System | Balanced accuracy | Flag precision | Supported precision | Coverage |
|---|---|---|---|---|
| Two judges | 0.795 (0.748 to 0.837) | 0.709 (0.656 to 0.757) | 0.929 (0.894 to 0.961) | 0.847 (0.818 to 0.875) |
| Quote judge alone | 0.751 (0.712 to 0.788) | 0.607 (0.558 to 0.654) | 0.916 (0.881 to 0.952) | 1.000 |
| Page judge alone | 0.777 (0.734 to 0.816) | 0.684 (0.629 to 0.733) | 0.890 (0.853 to 0.924) | 1.000 |

Two judges, with every 'needs a human' counted as wrong: balanced accuracy 0.688 (0.645 to 0.727). Labels: 212 supported, 141 not_found, 85 partial, 84 needs_human, 28 contradicted. Cost per claim, both judges: $0.00077. D-038 finish line (flag_precision 0.8, supported_precision 0.93, coverage 0.7): not passed.

| Sub-dataset | Two judges | Coverage | Quote alone | Page alone |
|---|---|---|---|---|
| AggreFact-CNN | 0.820 | 0.800 | 0.800 | 0.689 |
| AggreFact-XSum | 0.700 | 0.800 | 0.660 | 0.700 |
| ClaimVerify | 0.852 | 0.820 | 0.743 | 0.836 |
| ExpertQA | 0.566 | 0.920 | 0.550 | 0.601 |
| FactCheck-GPT | 0.699 | 0.980 | 0.721 | 0.676 |
| Lfqa | 0.870 | 1.000 | 0.870 | 0.870 |
| RAGTruth | 0.864 | 0.780 | 0.818 | 0.852 |
| Reveal | 0.987 | 0.900 | 0.988 | 0.929 |
| TofuEval-MediaS | 0.783 | 0.800 | 0.718 | 0.718 |
| TofuEval-MeetB | 0.882 | 0.820 | 0.781 | 0.845 |
| Wice | 0.722 | 0.700 | 0.614 | 0.828 |

### dev550: quote judge claude-haiku-5-5, page judge claude-haiku-5-5 (550 rows)

| System | Balanced accuracy | Flag precision | Supported precision | Coverage |
|---|---|---|---|---|
| Two judges | 0.786 (0.751 to 0.819) | 0.690 (0.637 to 0.742) | 0.934 (0.897 to 0.967) | 0.816 (0.784 to 0.847) |
| Quote judge alone | 0.720 (0.687 to 0.751) | 0.560 (0.511 to 0.608) | 0.922 (0.884 to 0.958) | 1.000 |
| Page judge alone | 0.776 (0.735 to 0.815) | 0.671 (0.619 to 0.721) | 0.900 (0.865 to 0.933) | 1.000 |

Two judges, with every 'needs a human' counted as wrong: balanced accuracy 0.655 (0.612 to 0.694). Labels: 181 supported, 143 not_found, 104 partial, 101 needs_human, 21 contradicted. Cost per claim, both judges: $0.00180. D-038 finish line (flag_precision 0.8, supported_precision 0.93, coverage 0.7): not passed.

| Sub-dataset | Two judges | Coverage | Quote alone | Page alone |
|---|---|---|---|---|
| AggreFact-CNN | 0.982 | 0.580 | 0.800 | 0.678 |
| AggreFact-XSum | 0.625 | 0.740 | 0.580 | 0.680 |
| ClaimVerify | 0.914 | 0.760 | 0.759 | 0.890 |
| ExpertQA | 0.635 | 0.940 | 0.634 | 0.647 |
| FactCheck-GPT | 0.640 | 0.920 | 0.611 | 0.676 |
| Lfqa | 0.862 | 0.960 | 0.834 | 0.870 |
| RAGTruth | 0.833 | 0.780 | 0.784 | 0.841 |
| Reveal | 0.963 | 0.940 | 0.902 | 0.941 |
| TofuEval-MediaS | 0.739 | 0.760 | 0.663 | 0.691 |
| TofuEval-MeetB | 0.872 | 0.840 | 0.801 | 0.845 |
| Wice | 0.582 | 0.760 | 0.550 | 0.778 |

Best thresholds on these rows (most coverage that meets the bars):

| Partial | Thresholds (supported / flag) | Flags right | Supported right | Coverage |
|---|---|---|---|---|
| partial counted as a flag | none meets the bars |  |  |  |
| partial as its own verdict | 0.85 / 0.8 | 0.807 | 0.940 | 0.824 |

### dev550: quote judge claude-haiku-5-5, page judge claude-haiku-5-5 (550 rows)

| System | Balanced accuracy | Flag precision | Supported precision | Coverage |
|---|---|---|---|---|
| Two judges | 0.794 (0.758 to 0.830) | 0.695 (0.641 to 0.744) | 0.940 (0.905 to 0.972) | 0.804 (0.769 to 0.835) |
| Quote judge alone | 0.720 (0.687 to 0.751) | 0.560 (0.511 to 0.608) | 0.922 (0.884 to 0.958) | 1.000 |
| Page judge alone | 0.777 (0.734 to 0.816) | 0.684 (0.629 to 0.733) | 0.890 (0.853 to 0.924) | 1.000 |

Two judges, with every 'needs a human' counted as wrong: balanced accuracy 0.645 (0.600 to 0.685). Labels: 183 supported, 142 not_found, 108 needs_human, 96 partial, 21 contradicted. Cost per claim, both judges: $0.00073. D-038 finish line (flag_precision 0.8, supported_precision 0.93, coverage 0.7): not passed.

| Sub-dataset | Two judges | Coverage | Quote alone | Page alone |
|---|---|---|---|---|
| AggreFact-CNN | 0.982 | 0.600 | 0.800 | 0.689 |
| AggreFact-XSum | 0.633 | 0.720 | 0.580 | 0.700 |
| ClaimVerify | 0.907 | 0.720 | 0.759 | 0.836 |
| ExpertQA | 0.631 | 0.920 | 0.634 | 0.601 |
| FactCheck-GPT | 0.640 | 0.920 | 0.611 | 0.676 |
| Lfqa | 0.862 | 0.960 | 0.834 | 0.870 |
| RAGTruth | 0.838 | 0.800 | 0.784 | 0.852 |
| Reveal | 0.962 | 0.920 | 0.902 | 0.929 |
| TofuEval-MediaS | 0.787 | 0.760 | 0.663 | 0.718 |
| TofuEval-MeetB | 0.872 | 0.840 | 0.801 | 0.845 |
| Wice | 0.624 | 0.680 | 0.550 | 0.828 |

### dev550: quote judge claude-haiku-5-5, page judge gpt-6-luna (550 rows)

| System | Balanced accuracy | Flag precision | Supported precision | Coverage |
|---|---|---|---|---|
| Two judges | 0.783 (0.750 to 0.814) | 0.677 (0.626 to 0.730) | 0.932 (0.895 to 0.967) | 0.829 (0.798 to 0.856) |
| Quote judge alone | 0.720 (0.687 to 0.751) | 0.560 (0.511 to 0.608) | 0.922 (0.884 to 0.958) | 1.000 |
| Page judge alone | 0.759 (0.720 to 0.798) | 0.651 (0.600 to 0.701) | 0.910 (0.875 to 0.943) | 1.000 |

Two judges, with every 'needs a human' counted as wrong: balanced accuracy 0.655 (0.614 to 0.694). Labels: 177 supported, 143 not_found, 114 partial, 94 needs_human, 22 contradicted. Cost per claim, both judges: $0.00060. D-038 finish line (flag_precision 0.8, supported_precision 0.93, coverage 0.7): not passed.

| Sub-dataset | Two judges | Coverage | Quote alone | Page alone |
|---|---|---|---|---|
| AggreFact-CNN | 0.982 | 0.580 | 0.800 | 0.678 |
| AggreFact-XSum | 0.611 | 0.820 | 0.580 | 0.680 |
| ClaimVerify | 0.879 | 0.680 | 0.759 | 0.781 |
| ExpertQA | 0.597 | 0.880 | 0.634 | 0.550 |
| FactCheck-GPT | 0.624 | 0.980 | 0.611 | 0.656 |
| Lfqa | 0.852 | 0.920 | 0.834 | 0.834 |
| RAGTruth | 0.847 | 0.840 | 0.784 | 0.875 |
| Reveal | 0.963 | 0.960 | 0.902 | 0.952 |
| TofuEval-MediaS | 0.800 | 0.800 | 0.663 | 0.790 |
| TofuEval-MeetB | 0.871 | 0.820 | 0.801 | 0.865 |
| Wice | 0.582 | 0.840 | 0.550 | 0.692 |

Best thresholds on these rows (most coverage that meets the bars):

| Partial | Thresholds (supported / flag) | Flags right | Supported right | Coverage |
|---|---|---|---|---|
| partial counted as a flag | none meets the bars |  |  |  |
| partial as its own verdict | 0.2 / 0.2 | 0.812 | 0.932 | 0.829 |

### dev550: quote judge claude-haiku-5-5, page judge gpt-6-luna (550 rows)

| System | Balanced accuracy | Flag precision | Supported precision | Coverage |
|---|---|---|---|---|
| Two judges | 0.787 (0.751 to 0.821) | 0.706 (0.653 to 0.755) | 0.926 (0.887 to 0.963) | 0.809 (0.774 to 0.842) |
| Quote judge alone | 0.720 (0.687 to 0.751) | 0.560 (0.511 to 0.608) | 0.922 (0.884 to 0.958) | 1.000 |
| Page judge alone | 0.783 (0.743 to 0.821) | 0.671 (0.621 to 0.720) | 0.913 (0.878 to 0.946) | 1.000 |

Two judges, with every 'needs a human' counted as wrong: balanced accuracy 0.659 (0.618 to 0.697). Labels: 176 supported, 142 not_found, 105 needs_human, 105 partial, 22 contradicted. Cost per claim, both judges: $0.00063. D-038 finish line (flag_precision 0.8, supported_precision 0.93, coverage 0.7): not passed.

| Sub-dataset | Two judges | Coverage | Quote alone | Page alone |
|---|---|---|---|---|
| AggreFact-CNN | 0.966 | 0.620 | 0.800 | 0.678 |
| AggreFact-XSum | 0.594 | 0.800 | 0.580 | 0.700 |
| ClaimVerify | 0.890 | 0.740 | 0.759 | 0.849 |
| ExpertQA | 0.602 | 0.900 | 0.634 | 0.596 |
| FactCheck-GPT | 0.661 | 0.920 | 0.611 | 0.734 |
| Lfqa | 0.868 | 0.880 | 0.834 | 0.830 |
| RAGTruth | 0.849 | 0.780 | 0.784 | 0.864 |
| Reveal | 0.963 | 0.940 | 0.902 | 0.941 |
| TofuEval-MediaS | 0.714 | 0.800 | 0.663 | 0.691 |
| TofuEval-MeetB | 0.901 | 0.780 | 0.801 | 0.890 |
| Wice | 0.650 | 0.740 | 0.550 | 0.841 |

## What failed

- Retrieval, lowest recall with hybrid + rerank: q34 (0.33), q25 (0.50), q16 (0.67), q21 (0.67), q26 (0.67), q33 (0.67).
- 16 pipeline claims were labelled supported but the judge did not agree. The first few:
  - Mount Everest's height was most recently measured in 2020 by a joint Nepalese and Chinese survey as 8,848.86 m. (judge: partial; The quote backs the 2020 joint Nepalese–Chinese survey measuring the height as 8,848.86 m, but it refers only to "its" height and never names Mount Everest.)
  - Cas9 nickases, which are Cas9 active-site mutants, can induce single-strand nicks instead of double-strand breaks. (judge: partial; The quote says Cas9 active-site mutants, also called Cas9 nickases, can induce single-strand nicks, but it never says this happens instead of double-strand breaks.)
  - Before the explosion, nearly all of the 211 control rods had been withdrawn, leaving the reactor in an extremely unstable state. (judge: partial; The quote states nearly all 211 control rods were withdrawn and the reactor was left extremely unstable, but it never mentions an explosion, so the 'before the explosion' timing is not backed.)
  - The Kessler syndrome is a scenario proposed by NASA scientists Donald J. Kessler and Burton G. Cour-Palais in 1978. (judge: partial; The quote states that a scenario was proposed by NASA scientists Donald J. Kessler and Burton G. Cour-Palais in 1978, but it is cut off before the subject, so it never says that this scenario is the Kessler syndrome.)
  - UDP is lightweight and simple, with no ordering of messages and no tracking of connections. (judge: partial; The quote states that the protocol is lightweight and very simple, with no message ordering and no connection tracking, but it never names UDP as the protocol being described.)
- The product's checker passed 1 of 50 deliberately broken claims as supported.
- It disagreed with the second model on 16 of 150 pairs.
  - p019 (changed_fact): reference partial, checker unsupported. During El Niño the trade winds strengthen and warm water is pushed back east toward the west coast of the Americas.
  - p020 (natural): reference supported, checker partial. In 1900 the average life expectancy of a newborn worldwide was 32 years, and by 2021 it had more than doubled to 71 years.
  - p034 (natural): reference supported, checker partial. The electrical energy supplied during charging is stored as chemical energy in the cell, with some loss.
  - p036 (changed_fact): reference partial, checker unsupported. The MDG1 target of halving extreme poverty rates was met five years early, with 400 million people lifted out of extreme poverty from 1990 to 2010.
  - p044 (natural): reference supported, checker partial. The rise has not been constant: the World Wars, the 1918 Spanish flu, HIV/AIDS and COVID-19 left a visible mark on life expectancy.
