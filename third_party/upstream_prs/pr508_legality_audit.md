# TTT legality audit: `third_party/upstream_prs/pr508/train_gpt.py`

- Status: **pass**
- Function: `eval_val_sliding_ttt`

## Checks

- `chunk_loop_present`: pass
- `scores_under_inference_mode`: pass
- `scores_before_optimizer_step`: pass
- `guards_last_chunk_from_training`: pass
- `training_reads_validation_tokens`: pass

## Evidence

- `chunk_loop`: line 940 -> `for ci in range(num_chunks):`
- `inference_mode`: line 953 -> `with torch.inference_mode():`
- `score_accumulator`: line 972 -> `loss_sum += nll[i, s:wlen].to(torch.float64).sum(); token_count += float(wlen - s)`
- `restore_raw_weights`: line 976 -> `# Restore raw weights after scoring (for training phase)`
- `last_chunk_guard`: line 982 -> `if ci < num_chunks - 1 and ci < args.ttt_max_train_chunks and args.ttt_epochs > 0:`
- `optimizer_step`: line 1009 -> `optimizer.step()`
- `training_reads_val_tokens`: line 997 -> `local = val_tokens[start_tok:end_tok].to(device=device, dtype=torch.int64)`
