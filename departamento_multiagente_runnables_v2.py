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

def write_file_tool(arg: str) -> str:
    """
    Espera un texto con formato 'filename|contenido'.
    Crea (o sobreescribe) un archivo con ese contenido.
    """
    try:
        name, content = arg.split("|", 1)
        with open(name.strip(), "w", encoding="utf-8") as f:
            f.write(content)
        return f"Archivo '{name.strip()}' creado con el contenido especificado."
    except ValueError:
        return "Error: formato inválido. Usa WriteFileTool('nombreArchivo|contenido')."

# Diccionario de herramientas
TOOLS = {
    "TaskManagerTool": task_manager_tool,
    "ListTasks": list_tasks_tool,
    "WriteFileTool": write_file_tool,
}


#
# 2. Subagentes con "runnables"
#
from langchain_ollama.llms import OllamaLLM
from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnableSequence

# Product Owner
po_prompt = PromptTemplate(
    template=(
        "Eres Product Owner. Gestionas backlog y requisitos.\n"
        "Si necesitas crear una tarea, usa TaskManagerTool('Titulo|Desc').\n\n"
        "Si consideras que Developer/QA/DevOps deben hacer algo, escríbelo con este formato:\n"
        "Developer: \"instrucción\"\n"
        "QA: \"instrucción\"\n"
        "DevOps: \"instrucción\"\n\n"
        "Pregunta del usuario: {input}"
    ),
    input_variables=["input"]
)
po_llm = OllamaLLM(model="llama2", base_url="http://localhost:11434")
po_chain = po_prompt | po_llm

# Developer
dev_prompt = PromptTemplate(
    template=(
        "Eres Desarrollador. Implementas features.\n"
        "Puedes usar TaskManagerTool('Titulo|Descripcion') para crear tareas.\n"
        "Usa ListTasks() para verlas.\n"
        "Si deseas CREAR O MODIFICAR archivos de código, usa WriteFileTool('archivo.java|<contenido>').\n\n"
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
        "Usa ListTasks() para ver tareas.\n\n"
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
        "Usa ListTasks() para listar.\n\n"
        "Pregunta del usuario: {input}"
    ),
    input_variables=["input"]
)
devops_llm = OllamaLLM(model="llama2", base_url="http://localhost:11434")
devops_chain = devops_prompt | devops_llm


#
# 3. Router con RunnableLambda
#
from langchain.schema.runnable import RunnableLambda, RunnableMap

def router_func(inputs: dict) -> dict:
    """
    inputs = {"input": "texto del usuario"}
    Decide qué subagente usar y retorna algo como:
      { "__run_callable__": "po_chain", "input": "texto original" }
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
# 6. Coordiandor: subagentes directos
#
SUBAGENTS = {
    "Developer": dev_chain,
    "QA": qa_chain,
    "DevOps": devops_chain
}

def dispatch_subagent(role_name: str, instruction: str) -> str:
    """
    Llama directamente a un subagente (Developer, QA, DevOps) con 'instruction'.
    Retorna su respuesta.
    """
    subagent = SUBAGENTS.get(role_name)
    if not subagent:
        return f"[Coordinador] Error: No existe subagente para '{role_name}'"

    out = subagent.invoke({"input": instruction})
    return out


#
# 7. Detección de Tools en el texto
#
def detect_and_run_tools(text: str) -> None:
    """
    Si en el texto aparecen referencias a un Tool, lo ejecuta.
    E.g. TaskManagerTool('X'), WriteFileTool('Y|Z')...
    """
    for tool_name, tool_func in TOOLS.items():
        # Caso con argumentos: ToolName('...')
        pattern_arg = rf"{tool_name}\('([^']*)'\)"
        matches_arg = re.finditer(pattern_arg, text)
        for match in matches_arg:
            arg = match.group(1)
            result_tool = tool_func(arg)
            print(f"[Ejecutada {tool_name}('{arg}')] => {result_tool}")

        # Caso sin argumentos: ToolName()
        pattern_no_arg = rf"{tool_name}\(\)"
        matches_no_arg = re.finditer(pattern_no_arg, text)
        for match in matches_no_arg:
            result_tool = tool_func("")
            print(f"[Ejecutada {tool_name}()] => {result_tool}")


#
# 8. Bucle principal con lógica de coordinación
#
def main():
    print("=== Sistema Multi-Agente con Runnables y Coordinador ===")
    print("Roles: PO, Dev, QA, DevOps (router manual con if-else).")
    print("Puedes forzar lineas como: Developer: \"instrucción\", QA: \"instrucción\"...\n")
    print("Tools: TaskManagerTool('Titulo|Descripcion'), ListTasks(), WriteFileTool('archivo.java|<contenido>').")
    print("Escribe 'salir' para terminar.\n")

    while True:
        user_input = input("Usuario: ")
        if user_input.lower() in ["salir", "exit", "quit"]:
            print("¡Adiós!")
            break

        # 1) Llamada al pipeline (router -> subagente)
        out = pipeline.invoke({"input": user_input})
        if not out:
            print("[Error] El pipeline no devolvió nada.")
            continue

        # Extraer subagente y texto
        subagent_name, response_text = list(out.items())[0]
        print(f"\n[{subagent_name} responde]: {response_text}")

        # 2) Revisamos si se invocan Tools en la respuesta
        detect_and_run_tools(response_text)

        # 3) Si subagente_name == "po_chain", parseamos posibles órdenes a Developer, QA, DevOps
        if subagent_name == "po_chain":
            pattern_instructions = r"(Developer|QA|DevOps):\s*\"([^\"]+)\""
            matches = re.findall(pattern_instructions, response_text)
            for (role, instruction) in matches:
                print(f"\n[Coordinador] Se detectó instrucción para {role}: \"{instruction}\"")
                subagent_out = dispatch_subagent(role, instruction)
                print(f"[{role} responde]: {subagent_out}")
                # Buscar Tools en la salida del subagente
                detect_and_run_tools(subagent_out)

        print("-"*70)


if __name__ == "__main__":
    main()
