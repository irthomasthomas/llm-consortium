import llm
try:
    model = llm.get_model('dummy')
    conv = model.conversation()
    response = conv.prompt("Hello", stream=False)
    print("Response text:", repr(response.text()))
except Exception as e:
    import traceback
    traceback.print_exc()
