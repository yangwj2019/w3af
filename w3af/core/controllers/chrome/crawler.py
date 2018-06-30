"""
crawler.py

Copyright 2018 Andres Riancho

This file is part of w3af, http://w3af.org/ .

w3af is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation version 2 of the License.

w3af is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with w3af; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

"""
import time

import w3af.core.controllers.output_manager as om

from w3af.core.controllers.chrome.pool import ChromePool
from w3af.core.data.fuzzer.utils import rand_alnum


class ChromeCrawler(object):
    """
    Use Google Chrome to crawl a site.

    The basic steps are:
        * Get an InstrumentedChrome instance from the chrome pool
        * Load a URL
        * Receive the HTTP requests generated during loading
        * Send the HTTP requests to the caller
    """

    def __init__(self, uri_opener):
        """

        :param uri_opener: The uri opener required by the InstrumentedChrome
                           instances to open URLs via the HTTP proxy daemon.
        """
        self._uri_opener = uri_opener
        self._pool = ChromePool(self._uri_opener)

    def crawl(self, url, http_traffic_queue):
        """
        :param url: The URL to crawl
        :param http_traffic_queue: Queue.Queue() where HTTP requests and responses
                                   generated by the browser are sent

        :return: True if the crawling process completed successfully, otherwise
                 exceptions are raised.
        """
        debugging_id = rand_alnum(8)

        args = (url, debugging_id)
        msg = 'Starting chrome crawler for %s (did: %s)'

        om.out.debug(msg % args)

        crawler_http_traffic_queue = CrawlerHTTPTrafficQueue(http_traffic_queue,
                                                             debugging_id=debugging_id)

        try:
            chrome = self._pool.get(http_traffic_queue=crawler_http_traffic_queue)
        except Exception, e:
            args = (e, debugging_id)
            msg = 'Failed to get a chrome instance: "%s" (did: %s)'
            om.out.debug(msg % args)

            raise ChromeCrawlerException('Failed to get a chrome instance: "%s"' % e)

        args = (chrome, url, debugging_id)
        om.out.debug('Using %s to load %s (did: %s)' % args)

        chrome.set_debugging_id(debugging_id)
        start = time.time()

        try:
            chrome.load_url(url)
        except Exception, e:
            args = (url, chrome, e, debugging_id)
            msg = 'Failed to load %s using %s: "%s" (did: %s)'
            om.out.debug(msg % args)

            # Since we got an error we remove this chrome instance from the pool
            # it might be in an error state
            self._pool.remove(chrome)

            args = (url, chrome, e)
            raise ChromeCrawlerException('Failed to load %s using %s: "%s"' % args)

        try:
            successfully_loaded = chrome.wait_for_load()
        except Exception, e:
            #
            # Note: Even if we get here, the InstrumentedChrome might have sent
            # a few HTTP requests. Those HTTP requests are immediately sent to
            # the output queue.
            #
            args = (url, chrome, e, debugging_id)
            msg = ('Exception raised while waiting for page load of %s '
                   'using %s: "%s" (did: %s)')
            om.out.debug(msg % args)

            # Since we got an error we remove this chrome instance from the pool
            # it might be in an error state
            self._pool.remove(chrome)

            args = (url, chrome, e)
            msg = ('Exception raised while waiting for page load of %s '
                   'using %s: "%s"')
            raise ChromeCrawlerException(msg % args)

        if not successfully_loaded:
            #
            # I need to pause the chrome browser so it doesn't continue loading
            #
            spent = time.time() - start
            msg = 'Chrome did not successfully load %s in %.2f seconds (did: %s)'
            args = (url, spent, debugging_id)
            om.out.debug(msg % args)

            try:
                chrome.stop()
            except Exception, e:
                msg = 'Failed to stop chrome browser %s: "%s" (did: %s)'
                args = (chrome, e, debugging_id)
                om.out.debug(msg % args)

                # Since we got an error we remove this chrome instance from the
                # pool it might be in an error state
                self._pool.remove(chrome)

                raise ChromeCrawlerException('Failed to stop chrome browser')

        # Success! Return the chrome instance to the pool
        self._pool.free(chrome)

        spent = time.time() - start
        args = (crawler_http_traffic_queue.count, url, spent, chrome, debugging_id)
        msg = 'Extracted %s new HTTP requests from %s in %.2f seconds using %s (did: %s)'
        om.out.debug(msg % args)

        return True

    def terminate(self):
        self._pool.terminate()
        self._uri_opener = None


class CrawlerHTTPTrafficQueue(object):
    def __init__(self, http_traffic_queue, debugging_id):
        self.http_traffic_queue = http_traffic_queue
        self.debugging_id = debugging_id
        self.count = 0

    def put(self, request_response):
        self.count += 1

        # msg = 'Received HTTP traffic from chrome in output queue. Count is %s (did: %s)'
        # args = (self.count, self.debugging_id)
        # om.out.debug(msg % args)

        return self.http_traffic_queue.put(request_response)


class ChromeCrawlerException(Exception):
    pass