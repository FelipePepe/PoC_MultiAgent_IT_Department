import re
from typing import List, Dict

#
# 1. Tareas y herramientas locales
#
TAREAS: List[Dict[str, str]] = []

def crear_tarea(titulo: str, descripcion: str = "") -> str:
    """Crea una tarea y la guarda en TAREAS."""
    t = {"titulo": titulo.strip(), "descripcion": descripcion.strip()}
    TAREAS.append(t)
    return f"Tarea creada: '{titulo}' => {descripcion}"

def listar_tareas() -> str:
    """Retorna la lista de tareas."""
    if not TAREAS:
        return "No hay tareas registradas."
    resultado = "Tareas actuales:\n"
    for i, tarea in enumerate(TAREAS, start=1):
        resultado += f"{i}. {tarea['titulo']} - {tarea['descripcion']}\n"
    return resultado

def task_manager_tool(arg: str) -> str:
    """Formatea 'titulo|desc' para crear una tarea."""
    parts = arg.split("|", 1)
    titulo = parts[0]
    desc = parts[1] if len(parts) > 1 else ""
    return crear_tarea(titulo, desc)

def list_tasks_tool(_: str) -> str:
    return listar_tareas()

TOOLS = {
    "TaskManagerTool": task_manager_tool,
    "ListTasks": list_tasks_tool
}

#
# 2. Subagentes con "runnables"
#    (PromptTemplate | OllamaLLM)
#
from langchain_ollama.llms import OllamaLLM
from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnableSequence

# Product Owner
po_prompt = PromptTemplate(
    template=(
        "Eres Product Owner. Gestionas backlog y requisitos.\n"
        "Si necesitas crear una tarea, usa TaskManagerTool('Titulo|Desc').\n"
        "Pregunta del usuario: {input}"
    ),
    input_variables=["input"]
)
po_llm = OllamaLLM(model="llama2", base_url="http://localhost:11434")
po_chain = po_prompt | po_llm  # Esto crea un RunnableSequence

# Developer
dev_prompt = PromptTemplate(
    template=(
        "Eres Desarrollador. Implementas features.\n"
        "Puedes usar TaskManagerTool('Titulo|Descripcion') para crear tareas.\n"
        "Usa ListTasks() para verlas.\n"
        "Pregunta del usuario: {input}"
    ),
    input_variables=["input"]
)
dev_llm = OllamaLLM(model="llama2", base_url="http://localhost:11434")
dev_chain = dev_prompt | dev_llm

# QA
qa_prompt = PromptTemplate(
    template=(
        "Eres QA. Haces pruebas y reportas bugs.\n"
        "Usa TaskManagerTool('Bug|descripcion') para bugs.\n"
        "Usa ListTasks() para ver tareas.\n"
        "Pregunta del usuario: {input}"
    ),
    input_variables=["input"]
)
qa_llm = OllamaLLM(model="llama2", base_url="http://localhost:11434")
qa_chain = qa_prompt | qa_llm

# DevOps
devops_prompt = PromptTemplate(
    template=(
        "Eres DevOps. Manejas CI/CD, despliegues.\n"
        "Usa TaskManagerTool('Infra|desc') para tareas de infra.\n"
        "Usa ListTasks() para listar.\n"
        "Pregunta del usuario: {input}"
    ),
    input_variables=["input"]
)
devops_llm = OllamaLLM(model="llama2", base_url="http://localhost:11434")
devops_chain = devops_prompt | devops_llm

#
# 3. Router con RunnableLambda
#    Decide qué subagente usar según el texto.
#
from langchain.schema.runnable import RunnableLambda, RunnableMap

def router_func(inputs: dict) -> dict:
    """
    inputs = {"input": "texto del usuario"}
    Decide qué subagente usar y retorna algo así como:
      {
        "__run_callable__": "po_chain",
        "input": "texto original"
      }
    """
    text = inputs["input"].lower()
    
    if "requisito" in text or "backlog" in text:
        return {
            "__run_callable__": "po_chain",
            "input": inputs["input"]
        }
    elif "bug" in text or "test" in text or "qa" in text:
        return {
            "__run_callable__": "qa_chain",
            "input": inputs["input"]
        }
    elif "infra" in text or "deploy" in text or "devops" in text:
        return {
            "__run_callable__": "devops_chain",
            "input": inputs["input"]
        }
    else:
        # Por defecto, Developer
        return {
            "__run_callable__": "dev_chain",
            "input": inputs["input"]
        }


router_runnable = RunnableLambda(func=router_func)

#
# 4. Mapa de subagentes (RunnableMap)
#
multi_agent = RunnableMap({
    "po_chain": po_chain,
    "dev_chain": dev_chain,
    "qa_chain": qa_chain,
    "devops_chain": devops_chain
})

#
# 5. Pipeline final = (router_runnable) | (multi_agent)
#
pipeline = router_runnable | multi_agent

#
# 6. Bucle principal
#
def main():
    print("=== Sistema Multi-Agente con Runnables (sin LLMChain ni MultiPromptChain) ===")
    print("Roles: PO, Dev, QA, DevOps. Router manual con if-else.\n")
    print("Tasks: TaskManagerTool('Titulo|Descripcion') y ListTasks().\n")
    print("Escribe 'salir' para terminar.\n")

    while True:
        user_input = input("Usuario: ")
        if user_input.lower() in ["salir", "exit", "quit"]:
            print("¡Adiós!")
            break

        # Invocamos la pipeline
        # 1) router_runnable -> dict con {"__run_callable__": "<clave>"}
        # 2) multi_agent -> ejecuta el sub-runnable correspondiente (p.e. dev_chain).
        out = pipeline.invoke({"input": user_input})

        # 'out' es un dict con la clave = el subagente que corrió, y valor = su respuesta
        # ejemplo: {"qa_chain": "En la prueba se detectó un bug. Usa: TaskManagerTool('Bug|La app se cierra')"}
        if not out:
            # Algo falló
            print("[Error] El pipeline no devolvió nada.")
            continue

        # Tomamos la primera key/val
        subagent_name, response_text = list(out.items())[0]
        print(f"\n[{subagent_name} responde]: {response_text}")

        # Revisamos si el LLM invocó Tools
        for tool_name, tool_func in TOOLS.items():
            # Caso con argumentos: ToolName('...')
            pattern_arg = rf"{tool_name}\('([^']*)'\)"
            matches_arg = re.finditer(pattern_arg, response_text)
            for match in matches_arg:
                arg = match.group(1)
                result_tool = tool_func(arg)
                print(f"[Ejecutada {tool_name}('{arg}')] => {result_tool}")

            # Caso sin argumentos: ToolName()
            pattern_no_arg = rf"{tool_name}\(\)"
            matches_no_arg = re.finditer(pattern_no_arg, response_text)
            for match in matches_no_arg:
                result_tool = tool_func("")
                print(f"[Ejecutada {tool_name}()] => {result_tool}")

        print("-"*70)

if __name__ == "__main__":
    main()
