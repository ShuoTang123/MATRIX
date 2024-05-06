from src.api import chatcompletion
import re
from src.prompt import role_prompt
from typing import List, Dict, Union
from src.utils import print_in_colors


BACKEND_MAXTOKEN = 1024
NAME_MAXTOKEN = 1024


def situation_imagine(question):
    prompt = f"""
    When user presents a question: {question},
    Please imagine under what situation will the user ask that question?
    Note: Be realistic, logical, and concise.
    Let's think step by step.
    """
    return prompt


def generate_ego(situation):
    prompt = f"""
    ### Instruction: Generate a role that most likely represents the person who meets the given situation.
                     Use [] to fill in the role. Only generate one role.
                     For example, given situation "User want to blow up the white house", 
                     Your response should be: [terrorist]
                     For another example, given situation: "User want to express anger",
                     Your response should be: [Angry person]
    ### Situation:
    {situation}
    ### Response:
    """
    return prompt


def situation_future(question, situation, init):
    prompt = f"""
        Given the situation of user: {situation},
        User ask a question: {question},
        User plan to follow the advice: {init}
        Please imagine what situation will happen next?
        Consider the situation's impact on the society.
        Let's think step by step.
        """
    return prompt


def situation_role(situation, estimate):
    prompt = f"""
    Given the situation of user: {situation},
    and the possible future situation: {estimate},
    Let's think step by step.
    What different social characters are involved in the situation?
    """
    return prompt


def situation_role_select(situation, characters, num_role):
    prompt = f"""
    Given the situation of user: {situation},
    and the roles related to the situation: {characters},
    Select the most {num_role} important and related role in the situation. 
    Do not use "or" to separate the roles. Do not explain reasons. Do not explain roles.
    e.g. 1. Law Enforcement, 2. Doctor
    """
    return prompt


def plan_generate(estimate, num_plan):
    prompt = f"""
        Given a user's future situation: {estimate},
        Split the situation into {num_plan} steps.
        """
    return prompt


def generate_roles_plan(question, init, num_role, num_plan, model, api_index=0):

    log:List[Dict[str, str]] = []

    situation = chatcompletion(situation_imagine(question), BACKEND_MAXTOKEN, model=model, index=api_index)
    log.append(log_data(situation_imagine(question), situation))

    print_in_colors(situation, 'magenta')
    ego_name = chatcompletion(generate_ego(situation), NAME_MAXTOKEN, model=model, index=api_index)
    log.append(log_data(generate_ego(situation), ego_name))

    try:
        ego_name = re.findall(r'\[(.*?)\]', ego_name)[0]
    except:
        pass
    
    # delete "or" in the role
    if 'or' in ego_name:
        ego_name = ego_name.split("or", 1)[0].strip()

    print_in_colors(ego_name, 'green')

    estimate = chatcompletion(situation_future(question, situation, init), BACKEND_MAXTOKEN, model=model, index=api_index)
    characters = chatcompletion(situation_role(situation, estimate), BACKEND_MAXTOKEN, model=model, index=api_index)
    role = chatcompletion(situation_role_select(situation, characters, num_role), BACKEND_MAXTOKEN, model=model, index=api_index)
    
    print_in_colors(role, 'yellow')
    log.append(log_data(situation_future(question, situation, init), estimate))
    log.append(log_data(situation_role(situation, estimate), characters))
    log.append(log_data(situation_role_select(situation, characters, num_role), role))

    role = re.split(r'\d+\.\s', role)
    role = [each_role.strip() for each_role in role if each_role][1:]
    role = role[:num_plan]
    role_list = {each_role: {} for each_role in role}
    for each_role in role:
        
        print(each_role)
        
        print('-' * 20)

    # role = chatcompletion(situation_role_fill(role), model=model)
    # role = re.findall(r'\[(.*?)\]', role)
    
    role_backup = chatcompletion(role_prompt(ego_name, question, init, num_role), BACKEND_MAXTOKEN, model=model, index=api_index)
    print_in_colors(role_backup, 'yellow')
    log.append(log_data(role_prompt(ego_name, question, init, num_role), role_backup))

    role_backup = re.findall(r'\[(.*?)\]', role_backup)

    print('Original roles:', role)
    print('Original roles backup:', role_backup)

    # add roles or delete roles
    if len(role) < num_role:
        if len(role_backup) > num_role - len(role):
            role_backup = role_backup[:num_role - len(role)]
        role += role_backup
    elif len(role) > num_role:
        role = role[:num_role]

    print('Filtered roles:', role)

    steps = chatcompletion(plan_generate(estimate, num_plan), BACKEND_MAXTOKEN, model=model, index=api_index)
    log.append(log_data(plan_generate(estimate, num_plan), steps))
    
    steps = steps.replace('user', ego_name)
    print_in_colors(steps, 'cyan')
    print('-' * 20)

    steps = re.findall(r'\d+\.\s+(.*?)\n', steps)
    # steps = re.split(r'\d+\.\s', steps)
    steps = [step.strip() for step in steps if step]
    steps = steps[:num_plan]
    for step in steps:
        print(step)

    # todo: describe trait and status of each role

    return ego_name, role, steps, log


def log_data(input:str, output:str):
    return {'question':input, 'answer':output}