/**
 * Kernel connector for variable and function introspection.
 */

import { ISessionContext } from '@jupyterlab/apputils';
import { KernelMessage } from '@jupyterlab/services';
import {
  IKernelConnector,
  IKernelConnectorFactory,
  IVariableInfo,
  IFunctionInfo
} from './tokens';

export type { IVariableInfo as VariableInfo, IFunctionInfo as FunctionInfo };
export type { IParameterInfo as ParameterInfo } from './tokens';

/**
 * Connects to a Jupyter kernel to introspect variables and functions.
 * Implements IKernelConnector for dependency injection.
 */
export class KernelConnector implements IKernelConnector {
  private _session: ISessionContext;

  constructor(session: ISessionContext) {
    this._session = session;
  }

  /**
   * Check if the kernel is available.
   */
  get kernelAvailable(): boolean {
    return !!this._session.session?.kernel;
  }

  /**
   * Execute code silently and capture output.
   */
  async execute(
    code: string,
    onOutput?: (msg: KernelMessage.IIOPubMessage) => void
  ): Promise<KernelMessage.IExecuteReplyMsg | null> {
    const kernel = this._session.session?.kernel;
    if (!kernel) {
      return null;
    }

    const content: KernelMessage.IExecuteRequestMsg['content'] = {
      code,
      stop_on_error: false,
      store_history: false,
      silent: true
    };

    const future = kernel.requestExecute(content);

    if (onOutput) {
      future.onIOPub = onOutput;
    }

    try {
      return (await future.done) as KernelMessage.IExecuteReplyMsg;
    } finally {
      future.dispose();
    }
  }

  /**
   * Execute code and return stdout output.
   */
  async executeAndCapture(code: string): Promise<string> {
    let output = '';

    await this.execute(code, (msg: KernelMessage.IIOPubMessage) => {
      const msgType = msg.header.msg_type;
      const content = msg.content as Record<string, unknown>;

      if (msgType === 'stream' && content.name === 'stdout') {
        output += content.text as string;
      } else if (msgType === 'execute_result') {
        const data = content.data as Record<string, string>;
        if (data && data['text/plain']) {
          output += data['text/plain'];
        }
      }
    });

    return output.trim();
  }

  /**
   * Get the value of a variable by name.
   */
  async getVariable(name: string): Promise<IVariableInfo | null> {
    const code = `
import json as _json_mod
try:
    _var = ${name}
    _result = {
        "name": "${name}",
        "type": type(_var).__name__,
        "repr": repr(_var)[:500]
    }
    print(_json_mod.dumps(_result))
    del _var, _result
except Exception as _e:
    print(_json_mod.dumps({"error": str(_e)}))
`;

    try {
      const output = await this.executeAndCapture(code);
      if (!output) {
        return null;
      }
      const result = JSON.parse(output);
      if (result.error) {
        console.warn(`Error getting variable ${name}:`, result.error);
        return null;
      }
      return result as IVariableInfo;
    } catch (e) {
      console.error(`Failed to get variable ${name}:`, e);
      return null;
    }
  }

  /**
   * Get information about a function.
   * Parses numpy/Google-style docstrings for parameter descriptions.
   */
  async getFunction(name: string): Promise<IFunctionInfo | null> {
    const code = `
import json as _json_mod
import inspect as _inspect_mod
import re as _re_mod
try:
    _func = ${name}
    if not callable(_func):
        print(_json_mod.dumps({"error": "Not callable"}))
    else:
        _sig = str(_inspect_mod.signature(_func))
        _doc = _inspect_mod.getdoc(_func) or "No documentation"
        
        # Parse docstring for parameter descriptions (numpy/Google style)
        _param_docs = {}
        try:
            _lines = _doc.splitlines()
            _in_params_section = False
            _current_param = None
            _current_desc = []
            
            for _line in _lines:
                _stripped = _line.strip()
                _lower = _stripped.lower()
                
                # Detect section headers
                if _lower in ('parameters', 'args', 'arguments', 'params'):
                    _in_params_section = True
                    continue
                elif _lower in ('returns', 'return', 'raises', 'examples', 'notes', 'see also', 'attributes'):
                    # End of parameters section
                    if _current_param and _current_desc:
                        _param_docs[_current_param] = ' '.join(_current_desc).strip()
                    _in_params_section = False
                    _current_param = None
                    _current_desc = []
                    continue
                
                if not _in_params_section:
                    continue
                
                # Skip section underlines (numpy style)
                if _stripped and all(c == '-' for c in _stripped):
                    continue
                
                # Check if this is a new parameter line
                # Numpy style: "param : type" or "param: type"
                # Google style: "param (type): description" or "param: description"
                _param_match = _re_mod.match(r'^(\\w+)\\s*(?:\\(.*?\\))?\\s*:(.*)$', _stripped)
                if _param_match and not _line.startswith(' ' * 4) or (_param_match and _line and _line[0] not in ' \\t'):
                    # Save previous param
                    if _current_param and _current_desc:
                        _param_docs[_current_param] = ' '.join(_current_desc).strip()
                    
                    _current_param = _param_match.group(1)
                    _rest = _param_match.group(2).strip()
                    _current_desc = [_rest] if _rest else []
                elif _current_param and _stripped:
                    # Continuation line
                    _current_desc.append(_stripped)
            
            # Save last param
            if _current_param and _current_desc:
                _param_docs[_current_param] = ' '.join(_current_desc).strip()
        except (AttributeError, TypeError, ValueError) as _parse_err:
            # Docstring parsing is best-effort; fall back to empty on parse failures
            _param_docs = {}
        
        _params = {}
        for _pname, _param in _inspect_mod.signature(_func).parameters.items():
            # Use parsed docstring description if available, otherwise use param name
            _desc = _param_docs.get(_pname, _pname)
            _pinfo = {"type": "string", "description": _desc}
            if _param.annotation != _inspect_mod.Parameter.empty:
                _ann = _param.annotation
                if hasattr(_ann, '__name__'):
                    _pinfo["type"] = _ann.__name__
                elif hasattr(_ann, '__origin__'):
                    _pinfo["type"] = str(_ann)
            if _param.default != _inspect_mod.Parameter.empty:
                _pinfo["default"] = repr(_param.default)
            _params[_pname] = _pinfo
        # Extract return type annotation
        _return_type = None
        _ret_ann = _inspect_mod.signature(_func).return_annotation
        if _ret_ann != _inspect_mod.Parameter.empty:
            if hasattr(_ret_ann, '__name__'):
                _return_type = _ret_ann.__name__
            elif hasattr(_ret_ann, '__origin__'):
                _return_type = str(_ret_ann)
            else:
                _return_type = str(_ret_ann)
        
        # Append return type to docstring (like toolslm pattern)
        _full_doc = _doc[:500]
        if _return_type:
            _full_doc += f"\\n\\nReturns:\\n- type: {_return_type}"
        
        _result = {
            "name": "${name}",
            "signature": _sig,
            "docstring": _full_doc,
            "parameters": _params,
            "return_type": _return_type
        }
        print(_json_mod.dumps(_result))
        del _func, _sig, _doc, _params, _result, _param_docs
except Exception as _e:
    print(_json_mod.dumps({"error": str(_e)}))
`;

    try {
      const output = await this.executeAndCapture(code);
      if (!output) {
        return null;
      }
      const result = JSON.parse(output);
      if (result.error) {
        console.warn(`Error getting function ${name}:`, result.error);
        return null;
      }
      return result as IFunctionInfo;
    } catch (e) {
      console.error(`Failed to get function ${name}:`, e);
      return null;
    }
  }
}

/**
 * Factory for creating KernelConnector instances.
 * Implements IKernelConnectorFactory for dependency injection.
 */
export class KernelConnectorFactory implements IKernelConnectorFactory {
  create(sessionContext: ISessionContext): IKernelConnector {
    return new KernelConnector(sessionContext);
  }
}
