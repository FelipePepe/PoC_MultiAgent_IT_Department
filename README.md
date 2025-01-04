# Sistema Multi-Agente con Runnables y Ollama
Este proyecto demuestra cómo crear un sistema multi-agente que simule los roles típicos de un departamento de desarrollo (Product Owner, Developer, QA y DevOps) empleando la arquitectura de Runnables de LangChain, junto con Ollama como modelo LLM local.

## 1. ¿Qué es este ejemplo?
* Objetivo: Permitir que diferentes “subagentes” (PO, Dev, QA, DevOps) respondan a diferentes consultas, cada uno con su propio contexto y lógica.
* Tecnología:
    * LangChain en su nueva API de “runnables”.
    * Ollama como modelo LLM local (ej. “llama2-7b” en http://localhost:11411).
* Características principales:
    * Router para decidir a qué subagente (rol) enviar la instrucción del usuario.
    * Subagentes definidos como PromptTemplate | OllamaLLM (sin LLMChain).
    * Herramientas (Tools) para crear y listar tareas, llamadas manualmente tras detectar patrones en la respuesta.
## 2. Arquitectura resumida
1. Herramientas:
    * TaskManagerTool('Título|Descripción') crea una tarea local.
    * ListTasks() muestra la lista de tareas acumuladas.
2. Subagentes:
    * POChain: PromptTemplate describiendo al Product Owner, seguido por OllamaLLM.
    * DevChain: Desarrollador.
    * QAChain: Tester/QA.
    * DevOpsChain: Despliegue e infra.

3. Router (RunnableLambda):
    * Función Python que analiza la instrucción del usuario y decide qué subagente se usará, retornando { "__run_callable__": "<subagente>", "input": "<texto usuario>" }.

4. Despachador (RunnableMap):
    * Contiene un mapeo de subagentes ("po_chain", "dev_chain", etc.).
    * Ejecuta el subagente que el router indica en __run_callable__.

5. Pipeline = router | multi_agent:
    * Primero se llama al router, que decide a qué subagente ir.
    * Luego se ejecuta el subagente, que genera la respuesta final.

## 3. Ejecución y pruebas
### 3.1. Requisitos
1. Tener Ollama corriendo localmente (por ejemplo):
```bash
ollama serve
```
Y verificar que escucha en http://localhost:11411.

2. Instalar las dependencias:

```bash
pip install -r requirements.txt
```

### 3.2. Ejecución
1. Ejecuta el script, por ejemplo:
```bash
python departamento_multiagente_runnables.py
```
2. Verás un prompt que dice algo como:
```java
=== Sistema Multi-Agente con Runnables (sin LLMChain ni MultiPromptChain) ===
Roles: PO, Dev, QA, DevOps. Router manual con if-else.

Tasks: TaskManagerTool('Titulo|Descripcion') y ListTasks().
Escribe 'salir' para terminar.
```
### 3.3. Pruebas sugeridas
A continuación, unos ejemplos de prompts y lo que deberías observar:

1. Product Owner
```
Usuario: Hola, necesito que definas requisitos para la nueva funcionalidad de pagos.
```
   * El router detecta “requisito” → subagente PO (po_chain).
   * Espera que el LLM responda algo como:

```
Para manejar estos requisitos, usaré TaskManagerTool('Pagos|Requerimos procesar pagos con tarjeta y PayPal')
```
    * Tu script detectará TaskManagerTool('Pagos|Requerimos...') y mostrará:
```
[Ejecutada TaskManagerTool('Pagos|Requerimos procesar...')] => Tarea creada: 'Pagos' => Requerimos...
```

2. Developer
```
Usuario: Necesito que implementes la funcionalidad de descuentos en el carrito.
```
* No detecta “requisito”/“bug”/“infra” → se va al subagente Developer (dev_chain).
* El LLM podría contestar algo como:
```
Perfecto, usaré TaskManagerTool('Descuento Carrito|Aplicar un 10% de descuento con cupón X')`
```
* Se crea la tarea “Descuento Carrito”.

3. QA
```
Usuario: Hay un bug en la búsqueda, por favor repórtalo.
```
* El router ve “bug” → subagente QA (qa_chain).
* Respuesta esperada:
```
Crearé la tarea: TaskManagerTool('Bug busqueda|La búsqueda falla con caracteres especiales')
```
* Aparece:
```
[Ejecutada TaskManagerTool('Bug busqueda|La búsqueda falla...')] => Tarea creada: 'Bug busqueda' => La búsqueda falla...
```
4. DevOps
```
Usuario: Configura la infraestructura para el despliegue de la app en producción.
```
* El router ve “infra”/“deploy” → subagente DevOps (devops_chain).
* LLM contesta:
```
Haré la tarea: TaskManagerTool('Infra|Preparar servidor con Docker y CI/CD')
```
5. ListTasks
```
Usuario: ListTasks()
```
* No coincide con “requisito”/“bug”/“infra” → subagente Developer por defecto (o depende de tu router if-else).
* El LLM subagente dev podría (en su respuesta) incluir ListTasks().
* Tu script lo detecta y llama list_tasks_tool("").
* Muestra algo como:
```
Tareas actuales:
1. Pagos - Requerimos procesar pagos con tarjeta y PayPal
2. Descuento Carrito - Aplicar un 10% de descuento con cupón X
3. Bug busqueda - La búsqueda falla con caracteres especiales
4. Infra - Preparar servidor con Docker y CI/CD
```
### 3.4. Comportamientos adicionales
* Si el router usa un simple if-else, puede malinterpretar algunas frases mixtas. Ajusta la lógica según tus palabras clave.
* Verifica que la conexión a http://localhost:11434 esté activa (si no, saldrá [WinError 10061]).
* El script termina escribiendo “salir”, “exit” o “quit” en el prompt.
### 4. Conclusiones
* Con este enfoque “runnable” no usamos LLMChain ni MultiPromptChain.
* Los subagentes se definen como PromptTemplate | OllamaLLM, y la orquestación se maneja con RunnableLambda (router) + RunnableMap.
* El mayor control recae en cómo definimos los prompts y la lógica del router.