# MATRIX
MATRIX: Self-Alignment of Large Language Models via Monopolylogue-based Social Scene Simulation

[Arxiv](https://arxiv.org/abs/2402.05699) | [Project Page](https://shuotang123.github.io/MATRIX/) 

**02/23/2024 update:** We release the preprint paper in arxiv, and the code is coming soon!

## Abstract
Aligning large language models (LLMs) with human values is imperative to mitigate potential adverse effects resulting from their misuse. Drawing from the sociological insight that acknowledging all parties’ concerns is a key factor in shaping human values, this paper proposes a novel direction to align LLMs by themselves: social scene simulation. To achieve this, we present MATRIX, a novel social scene simulator that emulates realistic scenes around a user’s input query, enabling the LLM to take social consequences into account before responding. MATRIX serves as a virtual rehearsal space, akin to a Monopolylogue, where the LLM performs diverse roles related to the query and practice by itself. To inject this alignment, we fine-tune the LLM with MATRIX-simulated data, ensuring adherence to human values without compromising inference speed. We theoretically show that the LLM with MATRIX outperforms Constitutional AI under mild assumptions. Finally, extensive experiments validate that our method outperforms over 10 baselines across 4 benchmarks. As evidenced by 875 user ratings, our tuned 13B-size LLM exceeds GPT-4 in aligning with human values.
<div style="text-align: center;">
    <img src="https://notes.sjtu.edu.cn/uploads/upload_b91f919711eba58d51dd00e5d6ea3734.png" width="70%" height="auto">
</div>


## MATRIX Framework
MATRIX takes an instruction-response pair as input and outputs the social consequences behind an instruction. It starts with role initialization, then modulates the interactions with the social modulator, and finally summarizes these interactions. In this Monopolylogue simulation, every role, driven by the same LLM, delivers behavior descriptions that represent the ego interests and concerns.
<div style="text-align: center;">
    <img src="https://notes.sjtu.edu.cn/uploads/upload_18435e3bb11449a07227a7fe193ba919.png" width="90%" height="auto">
</div>

## Experimental results
Pairwise comparisons between the LLM (30B) with MATRIX and 7 baselines. Win, Tie, Lose rates are reported with GPT-4 as the judger. The LLM with MATRIX consistently outperforms all of the baselines including GPT-3.5-Turbo on 4 evaluation datasets
![](https://notes.sjtu.edu.cn/uploads/upload_1909c5161c8c960cc4e7c1c1b92a4099.png)


Human evaluation experiments. This study selected 100 questions from 14 harmful categories in the Safe-RLHF dataset for assessment. 875 human ratings indicated that the 13B LLM, fine-tuned on MATRIX, surpassed the answer quality of GPT-4 when facing harmful questions.
<div style="text-align: center;">
    <img src="https://notes.sjtu.edu.cn/uploads/upload_b1d5e22b328fcd09f93ae8859bb46fbe.png" width="60%" height="auto">
</div>

## Todo
- [ ] Code release
- [ ] Data and model release

