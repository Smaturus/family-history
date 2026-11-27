function normalizedSearch(value) {
  return (value || '').toLocaleLowerCase('ru-RU').replace(/ё/g, 'е').replace(/[^a-zа-я0-9]+/gi, ' ').trim();
}

function loadPersonIndex() {
  if (loadPersonIndex.data) return loadPersonIndex.data;
  var node = document.getElementById('person-index');
  loadPersonIndex.data = node ? JSON.parse(node.textContent) : [];
  return loadPersonIndex.data;
}

function matchPeople(query, scope, treeKey) {
  var tokens = normalizedSearch(query).split(/\s+/).filter(Boolean);
  if (!tokens.length) return [];
  return loadPersonIndex().filter(function(person) {
    if (treeKey && !person.trees.some(function(tree) { return tree.key === treeKey; })) return false;
    if (scope && scope !== 'all' && !person.sections.some(function(section) { return section.key === scope; })) return false;
    var haystack = normalizedSearch(person.search);
    return tokens.every(function(token) { return haystack.indexOf(token) !== -1; });
  }).sort(function(a, b) {
    return a.name.localeCompare(b.name, 'ru') || a.id.localeCompare(b.id);
  });
}

function hideSearchResults(search) {
  var results = search.querySelector('.search-results');
  if (!results) return;
  results.hidden = true;
  var input = search.querySelector('input');
  if (input) input.setAttribute('aria-expanded', 'false');
}

function setNavSearchOpen(search, open) {
  var toggle = document.querySelector('[data-nav-search-toggle]');
  if (open) {
    search.removeAttribute('hidden');
    search.classList.add('is-open');
    if (toggle) toggle.setAttribute('aria-expanded', 'true');
    var input = search.querySelector('input');
    if (input) input.focus();
  } else {
    search.setAttribute('hidden', '');
    search.classList.remove('is-open');
    hideSearchResults(search);
    var input = search.querySelector('input');
    if (input) input.value = '';
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  }
  if (typeof measureNavHeight === 'function') measureNavHeight();
}

function placementFor(person, preferredTree) {
  var trees = person.trees || [];
  var index;
  for (index = 0; index < trees.length; index++) {
    if (trees[index].key === preferredTree) return trees[index];
  }
  return trees.length ? trees[0] : null;
}

function appendResultText(parent, person, showSection) {
  var nameEl = document.createElement('span');
  nameEl.className = 'result-name';
  nameEl.textContent = person.name;
  parent.appendChild(nameEl);
  if (person.years) {
    var yearsEl = document.createElement('span');
    yearsEl.className = 'result-years';
    yearsEl.textContent = person.years;
    parent.appendChild(yearsEl);
  }
  if (showSection && person.sections && person.sections.length) {
    var sectionEl = document.createElement('span');
    sectionEl.className = 'result-section';
    sectionEl.textContent = person.sections.map(function(section) { return section.title; }).join(' · ');
    parent.appendChild(sectionEl);
  }
}

function chooseSearchResult(search, button) {
  hideSearchResults(search);
  var cardId = button.getAttribute('data-card-id');
  if (!cardId) {
    openPerson(button.getAttribute('data-person-id'));
    return;
  }
  showPersonInTree(button.getAttribute('data-tree'), cardId);
}

function presentSearchMatches(search, matches, emptyText, appendMatches) {
  var input = search.querySelector('input');
  var results = search.querySelector('.search-results');
  results.textContent = '';
  if (!normalizedSearch(input.value)) {
    hideSearchResults(search);
    return;
  }
  if (!matches.length) {
    var empty = document.createElement('div');
    empty.className = 'search-empty';
    empty.textContent = emptyText;
    results.appendChild(empty);
  }
  appendMatches(results, matches);
  results.hidden = false;
  input.setAttribute('aria-expanded', 'true');
}

function renderSearchResults(search) {
  var input = search.querySelector('input');
  var localTree = search.getAttribute('data-search-tree');
  var matches = matchPeople(input.value, 'all', localTree);
  presentSearchMatches(search, matches, search.getAttribute('data-no-results') || '', function(results, people) {
    people.forEach(function(person) {
      var placement = placementFor(person, localTree);
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'search-result';
      button.setAttribute('role', 'option');
      button.setAttribute('aria-selected', 'false');
      button.setAttribute('data-person-id', person.id);
      if (placement) {
        button.setAttribute('data-card-id', placement.card);
        button.setAttribute('data-tree', placement.key);
      }
      appendResultText(button, person, false);
      button.addEventListener('click', function() { chooseSearchResult(search, button); });
      button.addEventListener('keydown', function(event) {
        if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
        event.preventDefault();
        var sibling = event.key === 'ArrowDown' ? button.nextElementSibling : button.previousElementSibling;
        if (sibling && sibling.classList.contains('search-result')) sibling.focus();
      });
      results.appendChild(button);
    });
  });
}

function closeNavSearchAfterAction(search, returnToResults) {
  if (returnToResults) {
    var input = search.querySelector('input');
    pendingPersonSearchReturn = {
      query: input.value,
      hash: window.location.hash || '#top'
    };
  }
  hideSearchResults(search);
  setNavSearchOpen(search, false);
}

function renderNavResults(search) {
  var input = search.querySelector('input');
  var matches = matchPeople(input.value, 'all', '');
  var inTreeLabel = search.getAttribute('data-in-tree') || '';
  presentSearchMatches(search, matches, search.getAttribute('data-no-results') || '', function(results, people) {
    people.forEach(function(person) {
      var row = document.createElement('div');
      row.className = 'search-result search-result-nav';
      row.setAttribute('role', 'option');
      var open = document.createElement('a');
      open.className = 'result-main';
      open.href = '#person-' + person.id;
      appendResultText(open, person, true);
      open.addEventListener('click', function() { closeNavSearchAfterAction(search, true); });
      row.appendChild(open);
      if (person.trees && person.trees.length) {
        var actions = document.createElement('div');
        actions.className = 'result-tree-actions';
        person.trees.forEach(function(tree) {
          var treeLink = document.createElement('a');
          treeLink.className = 'result-tree';
          treeLink.href = '#' + tree.key + '-tree';
          treeLink.setAttribute('data-show-tree', tree.key);
          treeLink.setAttribute('data-card-id', tree.card);
          treeLink.textContent = inTreeLabel + ' · ' + tree.title;
          treeLink.addEventListener('click', function() { closeNavSearchAfterAction(search); });
          actions.appendChild(treeLink);
        });
        row.appendChild(actions);
      }
      results.appendChild(row);
    });
  });
}

function bindSearchKeys(search, render) {
  var input = search.querySelector('input');
  var isNav = search.hasAttribute('data-person-search');
  input.addEventListener('input', function() {
    if (!normalizedSearch(input.value)) clearTreeHighlight();
    render(search);
  });
  input.addEventListener('focus', function() { render(search); });
  input.addEventListener('keydown', function(event) {
    var first = search.querySelector('button.search-result, a.result-main');
    if (event.key === 'ArrowDown' && first) {
      event.preventDefault();
      first.focus();
    } else if (event.key === 'Enter') {
      var open = search.querySelector('a.result-main');
      var button = search.querySelector('button.search-result');
      if (open) {
        event.preventDefault();
        openPerson(open.getAttribute('href').slice(8));
        if (isNav) closeNavSearchAfterAction(search, true);
        else hideSearchResults(search);
      } else if (button) {
        event.preventDefault();
        chooseSearchResult(search, button);
      }
    } else if (event.key === 'Escape') {
      hideSearchResults(search);
      if (isNav) setNavSearchOpen(search, false);
    }
  });
  input.addEventListener('blur', function() {
    setTimeout(function() {
      if (!search.contains(document.activeElement)) hideSearchResults(search);
    }, 150);
  });
}

function initSearch(search) {
  bindSearchKeys(search, renderSearchResults);
}

function initPersonSearch(search) {
  bindSearchKeys(search, renderNavResults);
  var toggle = document.querySelector('[data-nav-search-toggle]');
  var closeBtn = search.querySelector('[data-search-close]');
  if (toggle) {
    toggle.addEventListener('click', function() {
      setNavSearchOpen(search, !search.classList.contains('is-open'));
    });
  }
  if (closeBtn) {
    closeBtn.addEventListener('click', function() { setNavSearchOpen(search, false); });
  }
}