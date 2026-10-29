// Scripts do sistema Bela Casa Presentes

(function () {
  // ---------- máscaras dos campos ----------
  function soNumeros(v) { return v.replace(/\D/g, ''); }

  var mascaras = {
    cpf: function (v) {
      v = soNumeros(v).slice(0, 11);
      return v.replace(/(\d{3})(\d)/, '$1.$2')
              .replace(/(\d{3})(\d)/, '$1.$2')
              .replace(/(\d{3})(\d{1,2})$/, '$1-$2');
    },
    telefone: function (v) {
      v = soNumeros(v).slice(0, 11);
      if (v.length > 10) return v.replace(/(\d{2})(\d{5})(\d{4})/, '($1) $2-$3');
      if (v.length > 6) return v.replace(/(\d{2})(\d{4})(\d{0,4})/, '($1) $2-$3');
      if (v.length > 2) return v.replace(/(\d{2})(\d*)/, '($1) $2');
      return v;
    },
    cep: function (v) {
      v = soNumeros(v).slice(0, 8);
      return v.replace(/(\d{5})(\d)/, '$1-$2');
    }
  };

  document.querySelectorAll('[data-mascara]').forEach(function (campo) {
    var aplicar = mascaras[campo.dataset.mascara];
    campo.value = aplicar(campo.value);
    campo.addEventListener('input', function () { campo.value = aplicar(campo.value); });
  });

  // ---------- validação de CPF (mesma regra do servidor) ----------
  function cpfValido(cpf) {
    cpf = soNumeros(cpf);
    if (cpf.length !== 11 || /^(\d)\1{10}$/.test(cpf)) return false;
    for (var tam = 9; tam <= 10; tam++) {
      var soma = 0;
      for (var i = 0; i < tam; i++) soma += parseInt(cpf[i], 10) * (tam + 1 - i);
      var digito = (soma * 10 % 11) % 10;
      if (digito !== parseInt(cpf[tam], 10)) return false;
    }
    return true;
  }

  function mostrarErro(campo, mensagem) {
    var id = 'erro-' + campo.id;
    var span = document.getElementById(id);
    if (!span) {
      span = document.createElement('span');
      span.id = id;
      span.className = 'erro';
      campo.parentNode.appendChild(span);
    }
    span.textContent = mensagem;
    span.hidden = !mensagem;
    if (mensagem) {
      campo.setAttribute('aria-invalid', 'true');
      campo.setAttribute('aria-describedby', id);
    } else {
      campo.removeAttribute('aria-invalid');
    }
  }

  var formCliente = document.getElementById('form-cliente');
  if (formCliente) {
    var cpf = document.getElementById('cpf');
    cpf.addEventListener('blur', function () {
      mostrarErro(cpf, cpf.value && !cpfValido(cpf.value) ? 'CPF inválido.' : '');
    });
    formCliente.addEventListener('submit', function (e) {
      if (!cpfValido(cpf.value)) {
        e.preventDefault();
        mostrarErro(cpf, 'CPF inválido.');
        cpf.focus();
      }
    });
  }

  // ---------- consulta de CEP (API ViaCEP) ----------
  var botaoCep = document.getElementById('btn-cep');
  if (botaoCep) {
    var campoCep = document.getElementById('cep');
    var msg = document.getElementById('msg-cep');

    function buscarCep() {
      var cep = soNumeros(campoCep.value);
      msg.className = 'info';
      if (cep.length !== 8) {
        mostrarErro(campoCep, 'CEP deve ter 8 dígitos.');
        return;
      }
      mostrarErro(campoCep, '');
      msg.textContent = 'Consultando...';

      fetch('https://viacep.com.br/ws/' + cep + '/json/')
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.erro) {
            msg.textContent = 'CEP não encontrado. Preencha o endereço manualmente.';
            return;
          }
          document.getElementById('logradouro').value = d.logradouro || '';
          document.getElementById('bairro').value = d.bairro || '';
          document.getElementById('cidade').value = d.localidade || '';
          document.getElementById('estado').value = d.uf || '';
          msg.textContent = 'Endereço encontrado!';
          msg.className = 'info ok';
          document.getElementById('numero').focus();
        })
        .catch(function () {
          msg.textContent = 'Não foi possível consultar o CEP agora. Preencha manualmente.';
        });
    }

    botaoCep.addEventListener('click', buscarCep);
    campoCep.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); buscarCep(); }
    });
  }

  // ---------- formulário de pedido: preço e total ----------
  var selProduto = document.getElementById('produto_id');
  var campoValor = document.getElementById('valor_unitario');
  var campoQtd = document.getElementById('quantidade');
  var totalTela = document.getElementById('total-pedido');

  function paraNumero(texto) {
    var t = (texto || '').replace('R$', '').trim();
    if (t.indexOf(',') > -1) t = t.replace(/\./g, '').replace(',', '.');
    var n = parseFloat(t);
    return isNaN(n) ? 0 : n;
  }

  function atualizarTotal() {
    if (!totalTela) return;
    var total = paraNumero(campoValor.value) * (parseInt(campoQtd.value, 10) || 0);
    totalTela.textContent = total.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  if (selProduto && campoValor) {
    selProduto.addEventListener('change', function () {
      var preco = selProduto.options[selProduto.selectedIndex].dataset.preco;
      if (preco) campoValor.value = preco;
      atualizarTotal();
    });
    campoValor.addEventListener('input', atualizarTotal);
    campoQtd.addEventListener('input', atualizarTotal);
    atualizarTotal();
  }

  // ---------- confirmação antes de excluir ----------
  document.querySelectorAll('form[data-confirmar]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (!window.confirm(form.dataset.confirmar)) e.preventDefault();
    });
  });

  // ---------- exportar relatório (impressão / salvar como PDF) ----------
  var botaoImprimir = document.getElementById('btn-imprimir');
  if (botaoImprimir) {
    botaoImprimir.addEventListener('click', function () { window.print(); });
  }

  // ---------- acessibilidade: contraste e tamanho da letra ----------
  var raiz = document.documentElement;
  var botaoContraste = document.getElementById('btn-contraste');

  function guardar(chave, valor) {
    try { localStorage.setItem(chave, valor); } catch (e) {}
  }

  if (botaoContraste) {
    botaoContraste.setAttribute('aria-pressed', raiz.classList.contains('alto-contraste'));
    botaoContraste.addEventListener('click', function () {
      var ligado = raiz.classList.toggle('alto-contraste');
      botaoContraste.setAttribute('aria-pressed', ligado);
      guardar('contraste', ligado ? '1' : '0');
    });
  }

  function mudarFonte(passo) {
    var atual = parseInt(raiz.style.fontSize, 10) || 100;
    var novo = Math.min(150, Math.max(80, atual + passo));
    raiz.style.fontSize = novo + '%';
    guardar('fonte', String(novo));
  }
  var mais = document.getElementById('btn-fonte-mais');
  var menos = document.getElementById('btn-fonte-menos');
  if (mais) mais.addEventListener('click', function () { mudarFonte(10); });
  if (menos) menos.addEventListener('click', function () { mudarFonte(-10); });

  // atalhos Alt + número para o menu
  document.addEventListener('keydown', function (e) {
    if (!e.altKey || e.ctrlKey || e.metaKey) return;
    var link = document.querySelector('nav [data-tecla="' + e.key + '"]');
    if (link) { e.preventDefault(); window.location.href = link.href; }
  });
})();
