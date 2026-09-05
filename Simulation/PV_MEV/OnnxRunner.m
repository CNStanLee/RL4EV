classdef OnnxRunner < matlab.System
    % OnnxRunner  Run an ONNX model in Simulink through Python onnxruntime.
    %
    % Interpreted-execution MATLAB System block (no code generation).  One
    % input row vector (1 x NumIn, single) -> one output row vector
    % (1 x NumOut, single) = concatenation of all model outputs in order.
    % Needs pyenv pointing at an environment with onnxruntime (conda env
    % hgq2).  Used for the HGQ2 harmonic estimator (80 -> 8) and the EMI
    % detector (92 -> 16).  Exact by construction with respect to the ONNX
    % file; replace with a fixed-point implementation for HDL.
    properties (Nontunable)
        ModelFile = ''      % path to .onnx
        NumIn  = 80         % input vector length
        NumOut = 8          % total output length (all outputs concatenated)
        SampleTime = -1     % block sample time (s); -1 inherited
    end
    properties (Access = private)
        mf = ''        % cleaned model path; sessions are cached by path in onnx_bridge.py (a restored
                       % ModelOperatingPoint brings back block properties from an older session)
    end
    methods
        function obj = OnnxRunner(varargin)
            setProperties(obj, nargin, varargin{:});
        end
    end
    methods (Access = protected)
        function setupImpl(obj)
            here = fileparts(mfilename('fullpath'));
            sys = py.importlib.import_module('sys');
            if ~any(strcmp(cellfun(@char, cell(sys.path), 'UniformOutput', false), here)), sys.path.insert(int32(0), here); end
            br = py.importlib.import_module('onnx_bridge');   % no reload: several blocks share the session table
            % the block dialog may hand over the literal text including quotes
            mf = strtrim(char(string(obj.ModelFile))); mf = mf(mf ~= '''' & mf ~= '"');
            mf = OnnxRunner.resolve(mf);
            if ~isfile(mf), error('OnnxRunner: model file not found: %s', mf); end
            obj.mf = mf; br.ensure(mf, int32(1));
        end
        function y = stepImpl(obj, u)
            br = py.importlib.import_module('onnx_bridge');
            if isempty(obj.mf), m0 = strtrim(char(string(obj.ModelFile))); obj.mf = OnnxRunner.resolve(m0(m0 ~= '''' & m0 ~= '"')); end
            r = br.run_file(obj.mf, py.list(double(u(:)')), int32(obj.NumIn));
            y = single(cellfun(@double, cell(r)));
            y = y(1:obj.NumOut);
        end
        function releaseImpl(~)
        end
        function resetImpl(~)
        end
        function y = getOutputSizeImpl(obj), y = [1 obj.NumOut]; end
        function y = getOutputDataTypeImpl(~), y = 'single'; end
        function y = isOutputComplexImpl(~), y = false; end
        function y = isOutputFixedSizeImpl(~), y = true; end
        function sts = getSampleTimeImpl(obj)
            if obj.SampleTime > 0
                sts = createSampleTime(obj, 'Type', 'Discrete', 'SampleTime', obj.SampleTime);
            else
                sts = createSampleTime(obj, 'Type', 'Inherited');
            end
        end
        function flag = isInputDirectFeedthroughImpl(~, ~), flag = true; end
    end
    methods (Static)
        function mf = resolve(mf)
            % The block dialogs hold literal paths written on the machine that built the
            % subsystems (D:/Prj/RL4EV on Windows).  Map that prefix, or any absolute path
            % containing '/RL4EV/', onto the checkout this file lives in.
            if isfile(mf), return; end
            root = fileparts(fileparts(fileparts(mfilename('fullpath'))));   % .../RL4EV
            m = strrep(mf, '\', '/');
            k = strfind(m, '/RL4EV/');
            if ~isempty(k)
                cand = fullfile(root, m(k(1) + numel('/RL4EV/'):end));
                if isfile(cand), mf = cand; end
            end
        end
    end
    methods (Static, Access = protected)
        function simMode = getSimulateUsingImpl(), simMode = 'Interpreted execution'; end
        function flag = showSimulateUsingImpl(), flag = false; end
    end
end
